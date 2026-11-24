from bisect import bisect_right
from collections import OrderedDict

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QFrame

from .jobs import Job


ZOOM_MODES = {
    "actual": "100%",
    "window": "Fit to window",
    "width": "Fit to width",
    "height": "Fit to height",
}
SURROUND = QColor("#101114")
PAGE_BACKGROUND = QColor("#1b1d23")
PLACEHOLDER_TEXT = QColor("#aeb3be")
MARGIN = 16
CACHE_LIMIT = 160 * 1024 * 1024
ESTIMATED_SIZE = QSize(1000, 1450)


class PageView(QAbstractScrollArea):
    current_page_changed = Signal(int)
    page_rendered = Signal(int, int, object, object)

    def __init__(self, pool):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Manga pages")
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setSingleStep(40)

        self.pool = pool
        self.document = None
        self.index = 0
        self.strip = False
        self.zoom = "window"
        self.fullscreen = False
        self._generation = 0
        self._pending = None
        self._cache = OrderedDict()
        self._cache_size = 0
        self._costs = {}
        self._errors = {}
        self._sizes = []
        self._rects = []
        self._bottoms = []
        self._forward = True
        self._rebuilding = False
        self._layout_timer = QTimer(self, singleShot=True)
        self._layout_timer.timeout.connect(self._relayout)
        self.page_rendered.connect(self._receive_page, Qt.ConnectionType.QueuedConnection)

    def set_document(self, document):
        self._generation += 1
        self._pending = None
        self.document = document
        self._cache.clear()
        self._cache_size = 0
        self._costs.clear()
        self._errors.clear()
        self._sizes = [page.size for page in document.pages]
        self.index = 0
        self._forward = True
        self._rebuild((0, 0.0), reset_horizontal=True)
        self.current_page_changed.emit(0)

    def set_layout(self, strip):
        if self.strip == strip:
            return
        self.strip = strip
        self._rebuild((self.index, 0.0), reset_horizontal=True)

    def set_zoom(self, zoom):
        if self.zoom != zoom:
            anchor = self._anchor()
            self.zoom = zoom
            self._rebuild(anchor)

    def set_fullscreen(self, fullscreen):
        self.fullscreen = fullscreen
        self._layout_timer.start(0)

    def go_to(self, index):
        if not self.document:
            return
        index = max(0, min(index, len(self._sizes) - 1))
        if self.strip:
            horizontal = self.horizontalScrollBar()
            horizontal.setValue(horizontal.maximum() // 2)
            self.verticalScrollBar().setValue(self._page_top(index))
        else:
            self._set_index(index)
            self._rebuild((index, 0.0), reset_horizontal=True)

    def scroll_by(self, distance):
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + distance)

    def _set_index(self, index):
        if self.index != index:
            self._forward = index > self.index
            self.index = index
            self.current_page_changed.emit(index)

    def _index_at(self, y):
        return min(bisect_right(self._bottoms, y), len(self._bottoms) - 1)

    def _page_top(self, index):
        return self._rects[index].top() if self.strip and index else 0

    def _page_span(self, index):
        if self.strip:
            return self._bottoms[index] - self._page_top(index)
        return self._rects[0].height()

    def _anchor(self):
        if not self._rects:
            return self.index, 0.0
        top = self._page_top(self.index)
        fraction = (self.verticalScrollBar().value() - top) / self._page_span(self.index)
        return self.index, max(0.0, fraction)

    @Slot()
    def _relayout(self):
        self._rebuild(self._anchor())

    def _display_size(self, original, width, height):
        match self.zoom:
            case "width":
                scale = width / original.width()
            case "height":
                scale = height / original.height()
            case "window":
                scale = min(width / original.width(), height / original.height())
            case _:
                scale = 1 / self.viewport().devicePixelRatioF()
        return max(1, round(original.width() * scale)), max(1, round(original.height() * scale))

    def _set_scrollbar_policies(self, sizes):
        policy = Qt.ScrollBarPolicy
        if self.fullscreen:
            self.setHorizontalScrollBarPolicy(policy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(policy.ScrollBarAlwaysOff)
            return
        horizontal = policy.ScrollBarAsNeeded
        vertical = policy.ScrollBarAlwaysOn if self.strip else policy.ScrollBarAsNeeded
        if self.zoom in {"window", "width"}:
            horizontal = policy.ScrollBarAlwaysOff
        if self.zoom in {"window", "height"} and not self.strip:
            vertical = policy.ScrollBarAlwaysOff

        # Decide which bars are needed before they alter the viewport dimensions.
        # Otherwise fitting just at the scrollbar threshold can repeatedly resize it.
        width = self.contentsRect().width() - 2 * MARGIN
        height = max(1, self.contentsRect().height() - 2 * MARGIN)
        if self.zoom == "width" and not self.strip:
            _, fitted_height = self._display_size(sizes[0], max(1, width), height)
            vertical = policy.ScrollBarAlwaysOn if fitted_height > height else policy.ScrollBarAlwaysOff
        elif self.zoom == "height":
            if self.strip:
                width -= self.verticalScrollBar().sizeHint().width()
            too_wide = any(self._display_size(size, max(1, width), height)[0] > width for size in sizes)
            horizontal = policy.ScrollBarAlwaysOn if too_wide else policy.ScrollBarAlwaysOff

        self.setHorizontalScrollBarPolicy(horizontal)
        self.setVerticalScrollBarPolicy(vertical)

    def _rebuild(self, anchor, reset_horizontal=False):
        if not self.document:
            return
        margin = 0 if self.fullscreen else MARGIN
        sizes = self._sizes if self.strip else [self._sizes[self.index]]
        sizes = [size or ESTIMATED_SIZE for size in sizes]
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        pan = 0 if reset_horizontal else horizontal.value() - horizontal.maximum() // 2
        self._rebuilding = True
        try:
            self._set_scrollbar_policies(sizes)
            viewport = self.viewport().size()
            width = max(1, viewport.width() - 2 * margin)
            height = max(1, viewport.height() - 2 * margin)
            dimensions = [self._display_size(size, width, height) for size in sizes]
            content_width = max(viewport.width(), max(w for w, _ in dimensions) + 2 * margin)
            y = margin if self.strip else max(margin, (viewport.height() - dimensions[0][1]) // 2)
            self._rects = []
            self._bottoms = []
            for page_width, page_height in dimensions:
                x = (content_width - page_width) // 2
                self._rects.append(QRect(x, y, page_width, page_height))
                y += page_height
                self._bottoms.append(y)

            content_height = y + margin
            if self.strip:
                # Each page, including a short final page, can align at the top.
                content_height = max(content_height, self._page_top(len(dimensions) - 1) + viewport.height())
            horizontal.setPageStep(viewport.width())
            horizontal.setRange(0, min(2**31 - 1, max(0, content_width - viewport.width())))
            horizontal.setValue(horizontal.maximum() // 2 + pan)
            vertical.setPageStep(viewport.height())
            vertical.setRange(0, min(2**31 - 1, max(0, content_height - viewport.height())))
            span = self._page_span(anchor[0])
            offset = min(span - 1, round(span * anchor[1]))
            vertical.setValue(min(vertical.maximum(), self._page_top(anchor[0]) + offset))
        finally:
            self._rebuilding = False

        self._refresh()

    def _visible_pages(self):
        if not self.strip:
            return range(self.index, self.index + 1)
        top = self.verticalScrollBar().value()
        start = self._index_at(top)
        end = self._index_at(top + self.viewport().height() - 1)
        return range(start, end + 1)

    def _refresh(self):
        if self.strip:
            position = self.verticalScrollBar().value()
            self._set_index(self._index_at(position))
        self.viewport().update()
        self._request_page()

    def _request_page(self):
        if self._pending is not None or not self.document:
            return
        visible = self._visible_pages()
        adjacent = [visible.stop, visible.start - 1]
        if not self._forward:
            adjacent.reverse()
        working_size = sum(self._costs.get(index, 0) for index in [*visible, *adjacent])
        for index in [*visible, *adjacent]:
            if not 0 <= index < len(self._sizes) or index in self._cache or index in self._errors:
                continue
            if index not in visible and working_size >= CACHE_LIMIT:
                continue
            document = self.document
            generation = self._generation
            self._pending = index
            self.pool.start(Job(
                lambda: document.render(index),
                lambda result, error: self.page_rendered.emit(generation, index, result, error),
            ))
            return

    @Slot(int, int, object, object)
    def _receive_page(self, generation, index, result, error):
        if generation != self._generation:
            return
        self._pending = None
        if error:
            self._errors[index] = error
        else:
            image, size = result
            changed_size = self._sizes[index] != size
            self._sizes[index] = size
            self._cache[index] = image
            self._costs[index] = image.sizeInBytes()
            self._cache_size += self._costs[index]
            visible = self._visible_pages()
            for cached in list(self._cache):
                if self._cache_size <= CACHE_LIMIT:
                    break
                if cached not in visible and cached != index:
                    del self._cache[cached]
                    self._cache_size -= self._costs[cached]
            if changed_size and (self.strip or index == self.index):
                self._relayout()
                return
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_timer.start(0)

    def event(self, event):
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._layout_timer.start(0)
        return super().event(event)

    def scrollContentsBy(self, dx, dy):
        if self._rects and not self._rebuilding:
            self._refresh()

    def wheelEvent(self, event):
        horizontal = self.horizontalScrollBar()
        if (
            self.fullscreen
            and horizontal.maximum()
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            and not (event.pixelDelta().x() or event.angleDelta().x())
        ):
            distance = event.pixelDelta().y() or round(
                event.angleDelta().y() * QApplication.wheelScrollLines() * horizontal.singleStep() / 120
            )
            horizontal.setValue(horizontal.value() - distance)
            event.accept()
        else:
            super().wheelEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.fillRect(event.rect(), Qt.GlobalColor.black if self.fullscreen else SURROUND)
        if not self.document:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x_offset = self.horizontalScrollBar().value()
        y_offset = self.verticalScrollBar().value()
        viewport = self.viewport().rect()
        for index in self._visible_pages():
            rect = self._rects[index if self.strip else 0].translated(-x_offset, -y_offset)
            image = self._cache.get(index)
            if image is not None:
                self._cache.move_to_end(index)
                if image.hasAlphaChannel():
                    painter.fillRect(rect.intersected(viewport), Qt.GlobalColor.white)
                painter.drawImage(rect, image)
            else:
                painter.fillRect(rect.intersected(viewport), PAGE_BACKGROUND)
                painter.setPen(PLACEHOLDER_TEXT)
                message = self._errors.get(index, "Loading page…")
                painter.drawText(
                    rect.intersected(viewport).adjusted(12, 4, -12, -4),
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    message,
                )

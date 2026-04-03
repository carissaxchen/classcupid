/**
 * Drag-and-drop reorder for ranked rows; comparison card hover is CSS-only.
 */
(function () {
    function saveOrder(tbody) {
        var term = tbody.getAttribute("data-term");
        if (!term) return;
        var ids = [].map.call(
            tbody.querySelectorAll("tr.rank-sortable-row"),
            function (r) {
                return parseInt(r.getAttribute("data-course-id"), 10);
            }
        );
        fetch("/matches/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ term: term, order: ids }),
            credentials: "same-origin",
        }).then(function () {
            window.location.reload();
        });
    }

    function initSortable(tbody) {
        if (tbody.getAttribute("data-draggable") !== "1") return;

        var rows = [].slice.call(tbody.querySelectorAll("tr.rank-sortable-row"));
        var dragSrc = null;

        rows.forEach(function (row) {
            row.setAttribute("draggable", "true");
            row.addEventListener("dragstart", function (e) {
                dragSrc = row;
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", row.getAttribute("data-course-id") || "");
                row.classList.add("rank-dragging");
            });
            row.addEventListener("dragend", function () {
                row.classList.remove("rank-dragging");
                saveOrder(tbody);
                dragSrc = null;
            });
            row.addEventListener("dragover", function (e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (!dragSrc || dragSrc === row) return;
                var rect = row.getBoundingClientRect();
                var mid = rect.top + rect.height / 2;
                if (e.clientY < mid) {
                    tbody.insertBefore(dragSrc, row);
                } else {
                    tbody.insertBefore(dragSrc, row.nextSibling);
                }
            });
            row.addEventListener("drop", function (e) {
                e.preventDefault();
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("tbody.sortable-ranked").forEach(initSortable);
    });
})();

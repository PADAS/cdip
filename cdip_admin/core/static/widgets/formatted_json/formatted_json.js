(function () {
    function initCodeMirrorEditors() {
        document.querySelectorAll('textarea.fancy_json_textarea').forEach(function (textarea) {
            if (textarea.dataset.cmInitialized) return;
            textarea.dataset.cmInitialized = 'true';

            var rows = parseInt(textarea.getAttribute('rows'), 10) || 20;
            var cm = CodeMirror.fromTextArea(textarea, {
                mode: {name: 'javascript', json: true},
                lineNumbers: true,
                lineWrapping: true,
                matchBrackets: true,
                tabSize: 2,
                viewportMargin: Infinity
            });
            cm.setSize(null, (rows * 1.4) + 'em');
            var wrapper = cm.getWrapperElement();
            wrapper.style.border = '1px solid #adb5bd';
            wrapper.style.borderRadius = '.25rem';
            cm.on('change', function () { cm.save(); });
        });
    }

    document.addEventListener('DOMContentLoaded', initCodeMirrorEditors);
    document.addEventListener('htmx:afterSettle', initCodeMirrorEditors);
})();

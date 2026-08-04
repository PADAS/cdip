import string

from django import forms
from django.utils.safestring import mark_safe

# Same editor stack as gundi-portal (@monaco-editor/react), which loads
# Monaco from the jsDelivr CDN by default. Pin the version so admin pages
# don't shift under us when jsDelivr's "latest" moves.
MONACO_VERSION = "0.52.2"
MONACO_VS_BASE = f"https://cdn.jsdelivr.net/npm/monaco-editor@{MONACO_VERSION}/min/vs"

_WIDGET_TEMPLATE = string.Template(
    """
<div style="width: 60em; max-width: 100%;">
  $textarea
  <div id="$editor_id" style="height: $height; border: 1px solid #ccc; display: none;"></div>
</div>
<script>
(function () {
  var VS_BASE = "$vs_base";
  function withMonaco(cb) {
    if (window.monaco) { cb(window.monaco); return; }
    if (!window._monacoLoaderPromise) {
      window._monacoLoaderPromise = new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = VS_BASE + "/loader.js";
        s.onload = function () {
          window.require.config({ paths: { vs: VS_BASE } });
          // Monaco's workers can't be created cross-origin from a CDN
          // directly; the blob shim below is the documented workaround.
          window.MonacoEnvironment = {
            getWorkerUrl: function () {
              return URL.createObjectURL(new Blob([
                "self.MonacoEnvironment={baseUrl:'" + VS_BASE + "/../'};" +
                "importScripts('" + VS_BASE + "/base/worker/workerMain.js');"
              ], { type: "text/javascript" }));
            }
          };
          window.require(["vs/editor/editor.main"], function () { resolve(window.monaco); });
        };
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    window._monacoLoaderPromise.then(cb);
  }
  function init() {
    var textarea = document.getElementById("$widget_id");
    var container = document.getElementById("$editor_id");
    if (!textarea || !container || container.dataset.monacoMounted) { return; }
    container.dataset.monacoMounted = "1";
    withMonaco(function (monaco) {
      // If the CDN is unreachable this never runs and the plain
      // textarea stays usable as a fallback.
      textarea.style.display = "none";
      container.style.display = "block";
      var editor = monaco.editor.create(container, {
        value: textarea.value,
        language: "json",
        theme: "vs",
        // Mirrors gundi-portal's MONACO_OPTIONS
        // (src/components/connections/schema-builder/editorConfig.ts).
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineHeight: 20,
        padding: { top: 8 },
        readOnly: false,
        lineNumbers: "on",
        wordWrap: "off",
        automaticLayout: true,
        renderLineHighlight: "none",
        stickyScroll: { enabled: false },
        scrollbar: { useShadows: false },
        fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace"
      });
      editor.onDidChangeModelContent(function () {
        textarea.value = editor.getValue();
      });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
</script>
"""
)


class MonacoJSONWidget(forms.Textarea):
    """JSON editor matching gundi-portal's Monaco-based code editors.

    The real ``<textarea>`` stays in the form (hidden once Monaco mounts)
    and receives the editor's content on every change, so submission and
    server-side validation are untouched. If the CDN can't be reached the
    textarea remains visible as a plain-text fallback.
    """

    def __init__(self, attrs=None, height="30em"):
        self.height = height
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        textarea = super().render(name, value, attrs, renderer)
        widget_id = (attrs or {}).get("id") or f"id_{name}"
        return mark_safe(
            _WIDGET_TEMPLATE.substitute(
                textarea=textarea,
                widget_id=widget_id,
                editor_id=f"{widget_id}_monaco",
                height=self.height,
                vs_base=MONACO_VS_BASE,
            )
        )

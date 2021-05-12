$(document).ready(function() {
    var myButton = '<i id="copy-to-clip" title="Copy To Clipboard" class="fas fa-copy" onclick="copyToClipboard()"></i>';
    $(myButton).insertAfter($('#id_key'));
});

function copyToClipboard() {
    let copyText = document.getElementById("id_key");
    copyText.select();
    copyText.setSelectionRange(0, 99999);
    document.execCommand("copy");
    alert("Copied the text: " + copyText.value);
}
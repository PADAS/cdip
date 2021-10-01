$(document).ready(function () {
    $("#show_hide_password a").on('click', function (event) {
        event.preventDefault();
        let sensative_text = event.target.parentElement.parentElement.querySelector('input')
        let peakaboo = event.target.parentElement.parentElement.querySelector('.peakaboo')
        let clip_board = event.target.parentElement.parentElement.querySelector('.copy-to-clip')
        if ($(sensative_text).attr("type") == "text") {
            $(sensative_text).attr('type', 'password');
            $(peakaboo).addClass("fa-eye-slash");
            $(peakaboo).removeClass("fa-eye");
            $(clip_board).hide();
        } else if ($(sensative_text).attr("type") == "password") {
            $(sensative_text).attr('type', 'text');
            $(peakaboo).removeClass("fa-eye-slash");
            $(peakaboo).addClass("fa-eye");
            $(clip_board).show();
        }
    });
});

function copy_to_clipboard(event) {
    let element = event.target.parentElement.querySelector('input');
    element.select();
    element.setSelectionRange(0, 99999);
    document.execCommand("copy");

    let tooltip_element = event.target.querySelector('.tooltiptext');

    tooltip_element.innerHTML = "Copied!";
}


function reset_tooltip(event) {
    let tooltip_element = event.target.querySelector('.tooltiptext');
    setTimeout()
  tooltip_element.innerHTML = "Copy to clipboard";
}


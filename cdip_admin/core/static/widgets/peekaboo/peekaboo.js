function toggle_peekaboo(event) {
    event.preventDefault();
    let container = event.target.closest('#show_hide_password');
    let sensative_text = container.querySelector('input');
    let peakaboo = container.querySelector('.peakaboo');
    if (sensative_text.type == "text") {
        sensative_text.type = 'password';
        peakaboo.classList.add("fa-eye-slash");
        peakaboo.classList.remove("fa-eye");
    } else if (sensative_text.type == "password") {
        sensative_text.type = 'text';
        peakaboo.classList.remove("fa-eye-slash");
        peakaboo.classList.add("fa-eye");
    }
}

function copy_to_clipboard(event) {
    event.preventDefault();
    let container = event.target.closest('#show_hide_password');
    let element = container.querySelector('input');
    let value = element.value;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value);
    } else {
        element.type = 'text';
        element.select();
        element.setSelectionRange(0, 99999);
        document.execCommand("copy");
        element.type = 'password';
    }

    let tooltip_element = container.querySelector('.tooltiptext');
    if (tooltip_element) {
        tooltip_element.innerHTML = "Copied!";
    }
}

function reset_tooltip(event) {
    let tooltip_element = event.target.closest('.tooltiptarget');
    if (tooltip_element) {
        let span = tooltip_element.querySelector('.tooltiptext');
        if (span) {
            setTimeout(function() {
                span.innerHTML = "Copy to clipboard";
            }, 200);
        }
    }
}

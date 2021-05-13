$(document).ready(function() {
    $("#show_hide_password a").on('click', function(event) {
        event.preventDefault();
        let sensative_text = event.target.parentElement.parentElement.querySelector('input')
        let peakaboo = event.target.parentElement.parentElement.querySelector('.peakaboo')
        let clip_board = event.target.parentElement.parentElement.querySelector('.copy-to-clip')
        if($(sensative_text).attr("type") == "text"){
            $(sensative_text).attr('type', 'password');
            $(peakaboo).addClass( "fa-eye-slash" );
            $(peakaboo).removeClass( "fa-eye" );
            $(clip_board).hide();
        }else if($(sensative_text).attr("type") == "password"){
            $(sensative_text).attr('type', 'text');
            $(peakaboo).removeClass( "fa-eye-slash" );
            $(peakaboo).addClass( "fa-eye" );
            $(clip_board).show();
        }
    });
});

function copyToClipboard(event) {
    let r = document.createRange();
    let element = event.target.parentElement.querySelector('input')
    r.selectNode(element)
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(r);
    document.execCommand("copy");
}
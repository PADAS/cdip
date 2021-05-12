$(document).ready(function() {
    $("#show_hide_password a").on('click', function(event) {
        event.preventDefault();
        if($('#show_hide_password input').attr("type") == "text"){
            $('#show_hide_password input').attr('type', 'password');
            $('.peakaboo').addClass( "fa-eye-slash" );
            $('.peakaboo').removeClass( "fa-eye" );
        }else if($('#show_hide_password input').attr("type") == "password"){
            $('#show_hide_password input').attr('type', 'text');
            $('.peakaboo').removeClass( "fa-eye-slash" );
            $('.peakaboo').addClass( "fa-eye" );
        }
    });
});
const toasts = new Toasts({
    offsetX: 20,
    offsetY: 20,
    gap: 20,
    width: 300,
    timing: 'ease',
    duration: '.5s',
    dimOld: true,
    position: 'top-right'
});

$(document).ready(function()
{
    $(".btn").click(function()
    {
        $(".welcome-message").remove();
        $("form").show();
        $(this).attr('type', 'submit');
    });
});

$("form").submit(function(event)
{
    event.preventDefault();

    const password = $("#password").val();
    const confirmPassword = $("#cpassword").val();
    if (password !== confirmPassword) 
    {
        toasts.push({
            title: "Oops",
            content: "Password & Confirm Password not matched",
            style: "error",
            closeButton: false,
            dismissAfter: '3s'
        });
        return;
    }

    this.submit();
});
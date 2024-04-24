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
        alert("not matched");
        return;
    }

    this.submit();
});
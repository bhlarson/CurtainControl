var motors;
var groups;

$(function () {
    var temp = "myValue";
    var newOption = $('<option>');

    $.get("/GetMotors", function (serverMotors) {
        $.get("/GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;
            
            motors.forEach(function (motor, i) {
                $("#motorNames").append($("<option></option>").val(i).html(motor.name));
            });
            $('#motorNames :nth-child(1)').prop('selected', true);

            groups.forEach(function (group, i) {
                $("#groupNames").append($("<option></option>").val(i).html(group.name));
            });
            $('#groupNames :nth-child(1)').prop('selected', true);
        });
    });
});

function Open(){

}
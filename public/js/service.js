var socket = io();
socket.io._timeout = 30000;

var motors;
var groups;

$(function () {
    var temp = "myValue";
    var newOption = $('<option>');

    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;
            
            motors.forEach(function (motor, i) {
                $("#motorNames").append($("<option></option>").val(i).html(motor.name));
            });
            $("#motorNames")[0].selectedIndex = 0;

            //groups.forEach(function (group, i) {
            //    $("#groupNames").append($("<option></option>").val(i).html(group.name));
            //});
            //$("#groupNames")[0].selectedIndex = 0;
        });
    });
});

function Apply(){
    var command = {
        cmd: 'Jog', 
        type: 'motor', 
        addr: motors[$("#motorNames")[0].selectedIndex].address, 
        down: document.getElementById("down").checked, 
        time: document.getElementById("time").value
    };
    console.log(command);
    socket.emit('Action', command);
}
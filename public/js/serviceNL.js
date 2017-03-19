var socket = io();
socket.io._timeout = 30000;
var motors;

$(function () {
    
    
    $.get("/GetMotors", function (serverMotors) {
        motors = serverMotors;
        
        
        motors.forEach(function (motor, i) {
            $("#motorNames").append($("<option></option>").val(i).html(motor.name));
        });
        $("#motorNames")[0].selectedIndex = 0;
    });
}); function SendToServer() {   console.log("INSELECT");   } 
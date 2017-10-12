var socket = io(); socket.io._timeout = 30000; var motors;
var groups;  window.onload = Init;
function Init() {
    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;
        });
    });
}; function SendToServer() {   console.log("INSELECT");   } 
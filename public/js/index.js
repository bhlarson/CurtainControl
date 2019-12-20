var socket = io();
socket.io._timeout = 30000;

var motors;
var groups;

$('form').submit(function () {
    var direction = $("#MoveDirection").find(":selected").data("value");
    var window = $("#Window").find(":selected").data("value");
    console.log('move:' + direction + ' window:' + window);
    socket.emit('Action', {cmd: direction, type:window.type, addr: window.addr});
    return false;
});

function AddCmd(group, i) {
    var cmdDiv = document.getElementById("CmdButtons");
    var open = document.createElement('input');
    open.type = "button";
    open.value = group.name;
    open.onclick = function (){
        socket.emit('Action', { cmd: "UpLimit", type: "group", addr: group.address });
    };
    open.value = group.name + " Open";
    open.setAttribute("class", "MainCtrl");
    cmdDiv.appendChild(open);
    
    var close = document.createElement('input');
    close.type = "button";
    close.value = group.name;
    close.onclick = function(){
        socket.emit('Action', { cmd: "DownLimit", type: "group", addr: group.address });
    };
    close.value = group.name + " Close";
    close.setAttribute("class", "MainCtrl");
    cmdDiv.appendChild(close);
}

init();
function init() {
    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;

            groups.forEach(function (group, i) {
                AddCmd(group, i);
            });
        });
    });
}

function onWindowResize() {   
}
function onDocumentMouseMove(event) {
}
function onDocumentTouchStart(event) {
    if (event.touches.length === 1) {
    }
}
function onDocumentTouchMove(event) {
    if (event.touches.length === 1) {
    }
}


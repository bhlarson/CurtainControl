var socket = io();
socket.io._timeout = 30000;

var motors = [0x0671E4, 0x067C9F, 0x067121, 0x065F07,
    0x067944, 0x067D0E, 0x06796E, 0x067D0C, 0x067D0A, 
    0x06794F, 0x067982, 0x067984, 0x067981,
    0x067D0F, 0x067CD9, 0x0679D7, 0x0679D2, 0x06799B,
    0x06792F, 0x06793F, 0x067930, 0x06793B];

var motors1;
var groups;

/*
$(function () {
    
    var dateFormat = "yyyy-mm-dd",
        from = $("#from")
        .datepicker({
            defaultDate: "+1w",
            changeMonth: true,
            numberOfMonths: 3
        })
        .on("change", function () {
            to.datepicker("option", "minDate", getDate(this));
        }),
        to = $("#to").datepicker({
            defaultDate: "+1w",
            changeMonth: true,
            numberOfMonths: 3
        })
      .on("change", function () {
            from.datepicker("option", "maxDate", getDate(this));
        });
    
    function getDate(element) {
        var date;
        try {
            date = $.datepicker.parseDate(dateFormat, element.value);
        } catch (error) {
            date = null;
        }
        
        return date;
    }
   
    $("#MoveDirection").selectmenu({
        select: function (event, data) {
            console.log("MoveDirection " + data.item.label);
        }
    });
    
    $("#Window").selectmenu({
        select: function (event, data) {
                console.log("Window " + data.item.label);
        }
    });
    
    $("#eventSelect").selectmenu().selectmenu("menuWidget").css("height", "800px");
    $("#eventSelect").selectmenu({
        select: function (event, data) {
            console.log('eventSelect event:' + event + ' data:' + data);
        }
    });
    $("#ymax").change(function () {
        console.log('ymax change');
    });
    $("#ymin").change(function () {
        console.log('yminx change');
    });
    
    $("#eq > span").each(function (iSlider) {
        // read initial values from markup and remove that
        var value = parseInt($(this).text(), 10);
        $(this).slider({
            value: value,
            range: "min",
            animate: true,
            orientation: "vertical",
            change: function (event, ui) {
                console.log("Slider" + iSlider + "=" + ui.value);
                socket.emit('Action', { cmd: "Percent", type: "motor", addr: motors[iSlider], value: 100-ui.value});
            }
        });
    });
    $("#eq > input[type=checkbox]").each(function (iLock) {
        $(this).change(function (event, ui) {
            console.log('checkbox ' + iLock + ' changed to: ', $(this)[0].checked);
            if ($(this)[0].checked) {
                socket.emit('Action', { cmd: "Lock", type: "motor", addr: motors[iLock] });
            }
            else {
                socket.emit('Action', { cmd: "Unlock", type: "motor", addr: motors[iLock] });
            }
        });
        //input[0].onchange(function(event, data) {
        //    console.log('checkbox '+ iLock +' changed to: ', input.value);
        //});
        //$(this).input({
        //    change: function (event, ui) {
        //        console.log("Slider" + iLock + "=" + ui.value);
        //        socket.emit('Action', { cmd: "Lock", type: "motor"});
        //    }
        //});
    });

    $("#plotType").selectmenu({
        change: function (event, data) {
        }
    })
    .addClass("overflow");
    
});
*/
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
        socket.emit('Action', { cmd: "DownLimit", type: "group", addr: group.address
    });
    };
    close.value = group.name + " Close";
    close.setAttribute("class", "MainCtrl");
    cmdDiv.appendChild(close);
}

init();
function init() {
    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors1 = serverMotors;
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


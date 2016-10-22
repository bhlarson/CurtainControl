var socket = io();

socket.io._timeout = 30000;


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

    $("#plotType").selectmenu({
        change: function (event, data) {
        }
    })

    .addClass("overflow");
});

$('form').submit(function () {
    var direction = $("#MoveDirection").find(":selected").data("value");
    var window = $("#Window").find(":selected").data("value");
    console.log('move:' + direction + ' window:' + window);
    socket.emit('Action', {cmd: direction, type:window.type, addr: window.addr});
    return false;
});

init();
function init() {
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

var socket = io();
socket.io._timeout = 30000;

var motors;
var groups;

CommandEnum = {
    CTRL_MOVE : {
        msg: 0x01, name: "CTRL_MOVE", bytes: 3, data: {
            direction: { name: "Direction", bytes: 1, values: { 0: "Down Direction", 1: "Up Direction",  2: "Cancel"} }, 
            duration: { name: "Distance", bytes: 1, min: 0x0A, max: 0xFF },
            speed: { name: "speed", bytes: 1, values: { 0: "Up Speed", 1: "Down Speed", 2: "Slow Speed" } }
        }
    },
    CTRL_STOP : {
        msg: 0x02, name: "CTRL_STOP", bytes: 1, data: {}
    }, // In
    CTRL_MOVETO : {
        msg: 0x03, name: "CTRL_MOVETO", bytes: 4, data: {
            Function: { name: "Function", bytes: 1, values: { 0: "Down  Limit", 1: "Up Limit", 2: "Incremental Position" , 3: "Position Count", 4: "Position %"} }, 
            Position: { name: "Position", bytes: 1, min: 0x0001, max: 0xFFFF },
        }
    }, // In
    CTRL_MOVEOF : {msg:0x04, name:"CTRL_MOVEOF", bytes: 4, data: {}}, // In
    CTRL_WINK : {msg:0x05, name:"CTRL_WINK", bytes: 4, data: {}}, // In
    
    GET_MOTOR_POSITION : {msg:0x0C, name:"GET_MOTOR_POSITION", bytes: 4, data: {}}, // In
    POST_MOTOR_POSITION : {msg:0x0D, name:"POST_MOTOR_POSITION", bytes: 4, data: {}},
    GET_MOTOR_STATUS : {msg:0x0E, name:"GET_MOTOR_STATUS", bytes: 4, data: {}}, // In
    POST_MOTOR_STATUS : {msg:0x0F, name:"POST_MOTOR_STATUS", bytes: 4, data: {}},
    
    SET_MOTOR_LIMITS : {msg:0x11, name:"SET_MOTOR_LIMITS", bytes: 4, data: {}}, // In
    SET_MOTOR_DIRECTION : {msg:0x12, name:"SET_MOTOR_DIRECTION", bytes: 4, data: {}}, // In
    SET_MOTOR_ROLLING_SPEED : {msg:0x13, name:"SET_MOTOR_ROLLING_SPEED", bytes: 4, data: {}}, // In
    SET_MOTOR_IP : {msg:0x15, name:"SET_MOTOR_IP", bytes: 4, data: {}}, // In
    POST_DCT_LOCK : {msg:0x17, name:"POST_DCT_LOCK", bytes: 4, data: {}},
    
    GET_MOTOR_LIMITS : {msg:0x21, name:"GET_MOTOR_LIMITS", bytes: 4, data: {}},
    GET_MOTOR_DIRECTION : {msg:0x22, name:"GET_MOTOR_DIRECTION", bytes: 4, data: {}},
    GET_MOTOR_ROLLING_SPEED : {msg:0x23, name:"GET_MOTOR_ROLLING_SPEED", bytes: 4, data: {}},
    GET_MOTOR_IP : {msg: 0x25, name:"GET_MOTOR_IP", bytes: 4, data: {}},
    GET_DCT_LOCK : {msg: 0x27, name:"GET_DCT_LOCK", bytes: 4, data: {}},
    GET_FACTORY_DEFAULT : {msg:0x2F, name:"GET_FACTORY_DEFAULT", bytes: 4, data: {}},
    POST_MOTOR_LIMITS : {msg:0x31, name:"POST_MOTOR_LIMITS", bytes: 4, data: {}},
    POST_MOTOR_DIRECTION : {msg:0x32, name:"POST_MOTOR_DIRECTION", bytes: 4, data: {}},
    POST_MOTOR_ROLLING_SPEED : {msg:0x33, name:"POST_MOTOR_ROLLING_SPEED", bytes: 4, data: {}},
    POST_MOTOR_IP : {msg:0x35, name:"POST_MOTOR_IP", bytes: 4, data: {}},
    POST_FACTORY_DEFAULT : {msg:0x3F, name:"POST_FACTORY_DEFAULT", bytes: 4, data: {}},
    
    GET_LOCK : {msg:0x4B, name:"", bytes: 4, data: {}},
    SET_LOCK : {msg:0x5B, name:"", bytes: 4, data: {}},
    
    GET_NODE_ADDR : {msg:0x50, name:"", bytes: 4, data: {}},
    GET_GROUP_ADDR : {msg:0x51, name:"", bytes: 4, data: {}},
    GET_NODE_LABEL : {msg:0x55, name:"", bytes: 4, data: {}},
    GET_NODE_SERIAL_NUMBER : {msg:0x5C, name:"", bytes: 4, data: {}},
    ET_NETWORK_ERROR_STAT : {msg:0x5D, name:"", bytes: 4, data: {}},
    GET_NETWORK_STAT : {msg:0x5E, name: "", bytes: 4, data: {} }
};

window.onload = Init;
function Init() {
    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;
            
            motors.forEach(function (motor, i) {
                $("#motorNames").append($("<option></option>").val(i).html(motor.name));
            });
            $("#motorNames")[0].selectedIndex = 0;
            
            var i = 0;
            for (var key in CommandEnum) {
                $("#motorCommandSelect").append($("<option></option>").val(i).html(key));
                i++;
            }
            $("#motorCommandSelect")[0].selectedIndex = 0;


            if (motors && motors.constructor === Array) {
                SelectAddMotors("motorNames", motors);
            }

            ConfigureCommand();
        });
    });
};

function ConfigureCommand()
{
    var serviceForm = document.getElementById("MotorCommandOptions");
    while (serviceForm.children.length > 0) {
        serviceForm.removeChild(serviceForm.childNodes[0]);
    }
    
    var commandSelect = document.getElementById("motorCommandSelect");
    var key = commandSelect[Number(commandSelect.value)].innerText;
    var keyVal = CommandEnum[key];
    console.log("changed: " + JSON.stringify(keyVal));
    
    var keys = Object.keys(keyVal.data);
    keys.forEach(function (key) {
        var entry = keyVal.data[key];

        // Add Label
        var myLabel = document.createElement('label');
        myLabel.innerHTML = " "+entry.name +":";
        serviceForm.appendChild(myLabel);

        if (entry.values) {
            // Add select
            var selectList = document.createElement("select");
            serviceForm.appendChild(selectList);
            selectList.setAttribute("id", "mySelect");
            var array = Object.keys(entry.values);
            
            //Create and append the options
            for (var i = 0; i < array.length; i++) {
                var option = document.createElement("option");
                option.setAttribute("value", array[i]);
                option.text = entry.values[array[i]];
                selectList.appendChild(option);
            }
        }
        else {
            // Add input
            var addr = document.createElement('input');
            addr.type = "text";
            addr.pattern = "[a-fA-FxX0-9]";
            addr.value = entry.min;
            addr.max = entry.max;
            addr.min = entry.min;
            serviceForm.appendChild(addr);
        }
    });
}

function SelectAddMotors(selectId, motors) {
    var motorSelect = document.getElementById(selectId);
    motors.forEach(function (motor, i) {
        var option = document.createElement("option");
        option.text = motor.name;
        motorSelect.add(option);
    });
}

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
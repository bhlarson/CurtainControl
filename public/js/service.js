var socket = io();
socket.io._timeout = 30000;

var motors;
var groups;

CommandEnum = {
    CTRL_MOVE : {
        msg: 0x01, name: "CTRL_MOVE", bytes: 3, data: {
            direction: {
                name: "Direction", bytes: 1, values: {
                    0: "Down Direction", 
                    1: "Up Direction", 
                    2: "Cancel"
                }
            }, 
            duration: { name: "Duration", bytes: 1, min: 0x0A, max: 0xFF },
            speed: {
                name: "Speed", bytes: 1, values: {
                    0: "Up Speed", 
                    1: "Down Speed", 
                    2: "Slow Speed"
                }
            }
        }
    },
    CTRL_STOP : {
        msg: 0x02, name: "CTRL_STOP", bytes: 1, data: {
            Tilting: {
                name: "Tilting", bytes: 1, values: {
                    0: "Apply TILT_DEFAULT value", 
                    1: "No tilting"
                }
            }
        }
    }, // In
    CTRL_MOVETO : {
        msg: 0x03, name: "CTRL_MOVETO", bytes: 4, data: {
            Function: {
                name: "Function", bytes: 1, values: {
                    0: "Down  Limit", 
                    1: "Up Limit", 
                    2: "Incremental Position" , 
                    3: "Position Count", 
                    4: "Position %"
                }
            }, 
            Position: { name: "Position", bytes: 2, min: 0x0000, max: 0xFFFF },
            Tilting: {
                name: "Tilting", bytes: 1, values: {
                    0: "Apply TILT_DEFAULT value", 
                    0xFF: "No tilting"
                }
            } 
        }
    }, // In
    CTRL_MOVEOF : {
        msg: 0x04, name: "CTRL_MOVEOF", bytes: 4, data: {
            Function: {
                name: "Function", bytes: 1, values: {
                    0: "Next IP DOWN", 
                    1: "Next IP UP", 
                    2: "Jog DOWN (in pulses)" , 
                    3: "Jog UP (in pulses)", 
                    4: "Jog DOWN (in milliseconds)",
                    5: "Jog UP (in milliseconds)", 
                    6: "Tilt DOWN (in degrees)",
                    7: "Tilt UP (in degrees)"
                }
            }, 
            Position: { name: "Value", bytes: 2, min: 0x0001, max: 0xFFFF },
            Tilting: {
                name: "Tilting", bytes: 1, values: {
                    0: "Apply TILT_DEFAULT value", 
                    0xFF: "No tilting"
                }
            } 
        }
    }, // In
    CTRL_WINK : {msg:0x05, name:"CTRL_WINK", bytes: 0, data: {}}, // In
    GET_MOTOR_POSITION : {msg:0x0C, name:"GET_MOTOR_POSITION", bytes: 0, data: {}}, // In
    POST_MOTOR_POSITION : {
        msg: 0x0D, name: "POST_MOTOR_POSITION", bytes: 5, data: {
            Position_pulse: { name: "Position_pulse", bytes: 2, min: 0x0000, max: 0xFFFF },
            Position_percentage: { name: "Position_percentage", bytes: 1, min: 0x00, max: 0x64 },
            Tilting: { name: "Tilting", bytes: 1, min: 0x00, max: 0xFF },
            IP: { name: "IP", bytes: 1, min: 0x01, max: 0xFF }
        }
    },
    GET_MOTOR_STATUS : {msg:0x0E, name:"GET_MOTOR_STATUS", bytes: 0, data: {}}, // In
    POST_MOTOR_STATUS : {
        msg: 0x0F, name: "POST_MOTOR_STATUS", bytes: 4, data: {
            Status: {
                name: "Status", bytes: 1, values: {
                    0: "Stopped", 
                    1: "Running",
                    2: "Blocked", 
                    3: "Locked"
                }
            }, 
            Direction: {
                name: "Direction", bytes: 1, values: {
                    0: "Going DOWN", 
                    1: "Going UP",
                    0xFF: "Unknown"
                }
            }, 
            Source: {
                name: "Source", bytes: 1, values: {
                    0: "Internal", 
                    1: "Network message",
                    2: "DCT inputs"
                }
            }, 
            Cause: {
                name: "Cause", bytes: 1, values: {
                    0x00: "Target reached", 
                    0x01: "Explicit command",
                    0x02: "Wink",
                    0x10: "Limits not set",
                    0x11: "IP not set",
                    0x12: "Polarity not checked",
                    0x13: "Configuration mode",
                    0x20: "Obstacle detection",
                    0x21: "Over-current protection",
                    0x22: "Thermal protection",
                    0x30: "Run time exceeded",
                    0x31: "Out of range",
                    0x32: "Timeout exceeded",
                    0x80: "Encoder error occurred",
                    0x81: "No encoder pulses detected",
                    0xff: "Reset / PowerUp"
                }
            }
        }
    },
    SET_MOTOR_LIMITS : {msg:0x11, name:"SET_MOTOR_LIMITS", bytes: 4, data: {}}, // In
    SET_MOTOR_DIRECTION : {msg:0x12, name:"SET_MOTOR_DIRECTION", bytes: 4, data: {}}, // In
    SET_MOTOR_ROLLING_SPEED : {msg:0x13, name:"SET_MOTOR_ROLLING_SPEED", bytes: 4, data: {}}, // In
    SET_MOTOR_IP : {msg:0x15, name:"SET_MOTOR_IP", bytes: 4, data: {}}, // In
    POST_DCT_LOCK : {msg:0x17, name:"POST_DCT_LOCK", bytes: 4, data: {}},
    
    GET_MOTOR_LIMITS : {msg:0x21, name:"GET_MOTOR_LIMITS", bytes: 0, data: {}},
    GET_MOTOR_DIRECTION : {msg:0x22, name:"GET_MOTOR_DIRECTION", bytes: 0, data: {}},
    GET_MOTOR_ROLLING_SPEED : {msg:0x23, name:"GET_MOTOR_ROLLING_SPEED", bytes: 0, data: {}},
    GET_MOTOR_IP : {
        msg: 0x25, name: "GET_MOTOR_IP", bytes: 1, data: {
            IP_Index: { name: "IP_Index", bytes: 1, min: 0x01, max: 0x10 }
        }
    },
    GET_DCT_LOCK : {
        msg: 0x27, name: "GET_DCT_LOCK", bytes: 1, data: {
            UP_Limit: { name: "DCT_Index", bytes: 1, min: 0x01, max: 0xFF }
        }
    },
    GET_FACTORY_DEFAULT : {
        msg: 0x2F, name: "GET_FACTORY_DEFAULT", bytes: 1, data: {
            Function: {
                name: "Function", bytes: 1, values: {
                    0x00: "All settings", 
                    0x01: "Group addresses01",
                    0x02: "Group addresses02",
                    0x03: "Group addresses03",
                    0x04: "Group addresses04",
                    0x05: "Group addresses05",
                    0x06: "Group addresses06",
                    0x07: "Group addresses07",
                    0x08: "Group addresses08",
                    0x09: "Group addresses09",
                    0x10: "Group addresses10",
                    0x11: "Limits",
                    0x12: "Rotation polarity",
                    0x13: "Rolling speed",
                    0x15: "IPs",
                    0x17: "Locks"
                }
            }
        }
    },
    POST_MOTOR_LIMITS : {
        msg: 0x31, name: "POST_MOTOR_LIMITS", bytes: 4, data: {
            UP_Limit: { name: "UP_Limit", bytes: 2, min: 0x0000, max: 0xFFFF },
            DOWN_Limit: { name: "DOWN_Limit", bytes: 2, min: 0x0000, max: 0xFFFF }
        }
    },
    POST_MOTOR_DIRECTION : {
        msg: 0x32, name: "POST_MOTOR_DIRECTION", bytes: 1, data: {
            Direction: {
                name: "Direction", bytes: 1, values: {
                    0x00: "Standard rotation", 
                    0x01: "Reversed rotation"
                }
            }
        }
    },
    POST_MOTOR_ROLLING_SPEED : {
        msg: 0x33, name: "POST_MOTOR_ROLLING_SPEED", bytes: 3, data: {
            UP_Speed: { name: "UP_Speed", bytes: 1, min: 6, max: 28 },
            DOWN_Speed: { name: "DOWN_Speed", bytes: 1, min: 6, max: 28 },
            Slow_Speed: { name: "Slow_Speed", bytes: 1, min: 6, max: 28 }
    }},
    POST_MOTOR_IP : {
        msg: 0x35, name: "POST_MOTOR_IP", bytes: 4, data: {
            IP_index: { name: "IP_index", bytes: 1, min: 0, max: 0x10 },
            IP_pulse: { name: "IP_pulse", bytes: 2, min: 0, max: 0xFFFF },
            IP_percentage: { name: "IP_percentage", bytes: 1, min: 0, max: 100 }
        }
    },
    POST_DCT_LOCK_STATUS : {
        msg: 0x37, name: "POST_DCT_LOCK_STATUS", bytes: 5, data: {
            Status: { name: "Status", bytes: 1, min: 0, max: 0x01 },
            Source_Addr: { name: "Source_Addr", bytes: 3, min: 0, max: 0xFFFF },
            Priority: { name: "Priority", bytes: 1, min: 0, max: 0xFF }
        }
    },
    POST_FACTORY_DEFAULT : {
        msg: 0x3F, name: "POST_FACTORY_DEFAULT", bytes: 2, data: {
            Function: { name: "Function", bytes: 1, values: {
                    0x00: "All settings", 
                    0x01: "Group addresses01",
                    0x02: "Group addresses02",
                    0x03: "Group addresses03",
                    0x04: "Group addresses04",
                    0x05: "Group addresses05",
                    0x06: "Group addresses06",
                    0x07: "Group addresses07",
                    0x08: "Group addresses08",
                    0x09: "Group addresses09",
                    0x10: "Group addresses10",
                    0x11: "Limits",
                    0x12: "Rotation polarity",
                    0x13: "Rolling speed",
                    0x15: "IPs",
                    0x17: "Locks"
                }
            },
            Status: { name: "Status", bytes: 1, values: {
                    0x00: "Different from default values", 
                    0x01: "Default values"
                }
            }
        }
    },
    
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
    var currentCommand = CommandEnum[key];
    console.log("changed: " + JSON.stringify(currentCommand));
    
    var keys = Object.keys(currentCommand.data);
    keys.forEach(function (key) {
        var entry = currentCommand.data[key];

        // Add Label
        var myLabel = document.createElement('label');
        myLabel.innerHTML = " "+entry.name +":";
        serviceForm.appendChild(myLabel);

        if (entry.values) {
            // Add select
            var selectList = document.createElement("select");
            serviceForm.appendChild(selectList);
            selectList.setAttribute("id", entry.name);
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
            addr.setAttribute("id", entry.name);

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

function MotorCommand(){
    var commandSelect = document.getElementById("motorCommandSelect");
    var key = commandSelect[Number(commandSelect.value)].innerText;
    var currentCommand = CommandEnum[key];
    console.log("changed: " + JSON.stringify(currentCommand));
 
    var keys = Object.keys(currentCommand.data);
    var motorData = new Uint8Array(keys.length);

    var i = 0;
    keys.forEach(function (key) {
        var entry = currentCommand.data[key];
        var entryElement = document.getElementById(entry.name);

        if (entry.values) {
            motorData[i] = Number(Object.keys(entry.values)[entryElement.selectedIndex]);
            i++;
        }
        else {
            // Add input
            var value = parseInt(entryElement.value, 16);
            for (var j = 0; j < entry.bytes; j++) {
                motorData[i] = 0xFF & value;
                value = value >> 8;
                i++;
            }
        }
    });


    var command = {
        cmd: currentCommand.msg, 
        type: 'motor', 
        addr: motors[document.getElementById("motorNames").selectedIndex].address, 
        data: motorData
    };
    console.log(command);
    socket.emit('Action', command);
}
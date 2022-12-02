var motors;
var groups;

function AppendDevice(row, motor, newDevice)
{
    const iAddr = 0;
    const iName  = 1;
    const iDesc = 2;
    const iType = 3;
    const iInstall = 4;
    const iAngle = 5;
    const iDist = 6;
    const iControl = 7;
    
    while (row.cells && row.cells.length > 0) {
        row.deleteCell(row.cells.length-1);
    }

    if (typeof motor === 'undefined' || motor === null) {
        motor = { address:0, name:'', description:'', type:'', date:Date(), angle:0, distance:0};
    }
    var addr = document.createElement('input');
    addr.type = "text";
    addr.pattern = "[a-fA-FxX0-9]";
    addr.value = "0x"+motor.address.toString(16);
    addr.max = 0xFFFFFF;
    addr.min = 0x000001;
    var cell = row.insertCell(iAddr);
    cell.appendChild(addr);

    var name = document.createElement('input');
    name.type = "text";
    name.value = motor.name;
    var cell = row.insertCell(iName);
    cell.appendChild(name);

    var desc = document.createElement('input');
    desc.type = "text";
    desc.value = motor.description;
    var cell = row.insertCell(iDesc);
    cell.appendChild(desc);
       
    //Create and append select list
    var type = document.createElement("select");   
    var typeOptions = ["ST30 RS485", "SDN Switch"]; //Create array of options to be added
    //Create and append the options
    for (var i = 0; i < typeOptions.length; i++) {
        var option = document.createElement("option");
        option.value = typeOptions[i];
        option.text = typeOptions[i];
        type.appendChild(option);
    }
    
    if ((typeof motor.type === 'undefined' || motor.type === null)) {
        type.value = typeOptions[0];
    }
    else {
        type.value = motor.type;
    }
    var cell = row.insertCell(iType);
    cell.appendChild(type);

    var date = document.createElement('input');
    date.type = "date";
    if ((typeof motor.install === 'undefined' || motor.install === null)) {
        var now = new Date();
        date.value = now.toISOString().substr(0, 10);
    }
    else {
        date.value = motor.install.substr(0, 10);
    }
    var cell = row.insertCell(iInstall);
    cell.appendChild(date);

    var angle = document.createElement('input');
    angle.type = "number";
    if ((typeof motor.angle === 'undefined' || motor.angle === null)) {
        angle.value = 0;
    }
    else {
        angle.value = motor.angle;
    }
    var cell = row.insertCell(iAngle);
    cell.appendChild(angle);
    
    var distance = document.createElement('input');
    distance.type = "number";
    if ((typeof motor.distance === 'undefined' || motor.distance === null)) {
        distance.value = 0;
    }
    else {
        distance.value = motor.distance;
    }
    var cell = row.insertCell(iDist);
    cell.appendChild(distance);
    var cell = row.insertCell(iControl);
    if (!(typeof newDevice === 'undefined' || newDevice === null)) {
        var add = document.createElement('input');
        add.type = "button";
        add.value = "Add";
        add.onclick = function () {
            
            var update = {
                address: parseInt(addr.value),
                name: name.value,
                description: desc.value,
                type: type.value,
                distance: Number(distance.value),
                install: date.value,
                angle: Number(angle.value)
            };
            
            $.get("AddDevice", { update: update }, function (err) {
                if (err) {
                    console.log(Date() + " AddDevice failed:");
                    console.log(err);
                }
                else {
                    AppendDevice(row, update);
                }
            });
        };
        cell.appendChild(add);
    }
    else {
        var update = document.createElement('input');
        update.type = "button";
        update.value = "Update";
        update.onclick = function () {
            
            var update = {
                address: Number(addr.value),
                name: name.value,
                description: desc.value,
                type: type.value,
                distance: Number(distance.value),
                install: date.value,
                angle: Number(angle.value)
            };
            
            $.get("UpdateDevice", { previous: motor, update: update }, function (err) {
                console.log("UpdateDevice err:" + err);
            });
        };
        cell.appendChild(update);
    }
    var remove = document.createElement('input');
    remove.type = "button";
    remove.value = "Delete";
    remove.onclick = function () {
        
        var remove = {
            address: Number(addr.value),
        };
        
        $.get("RemoveDevice", remove, function (err) {
            if (err) {
                console.log(Date() + " RemoveDevice failed:");
                console.log(err);
            }
            else {
                var table = document.getElementById("deviceTable");
               table.deleteRow(row.rowIndex);
            }
        });
    };
    cell.appendChild(remove);
}

function GetDeviceNames(devices)
{
    var names = [];
    if (devices && devices.constructor === Array) {
        devices.forEach(function (device, i) {
            names[i] = device.name;
        });
    }
    return names;
}

function AppendGroup(row, group, newGroup) {
    // Clear out the row if it already exists
    while (row.cells && row.cells.length > 0) {
        row.deleteCell(row.cells.length - 1);
    }

    const iAddr = 0;
    const iName  = 1;
    const iDesc = 2;
    const iNumDevices = 3;
    const iDevices = 4;
    const iControl = 5;
    
    var cellAddress = row.insertCell(iAddr);
    var cellName = row.insertCell(iName);
    var cellDesc = row.insertCell(iDesc);
    var cellNumDevices = row.insertCell(iNumDevices);
    var cellGroup = row.insertCell(iDevices);
    var cellControl = row.insertCell(iControl);
    
    if (typeof group === 'undefined' || group === null) {
        group = { address: 0, name: '', description: '', devices: [] };
    }
    var addr = document.createElement('input');
    addr.type = "text";
    addr.pattern = "[a-fA-FxX0-9]";
    addr.value = "0x"+group.address.toString(16);
    addr.max = 0xFFFFFF;
    addr.min = 0x000001;
    cellAddress.appendChild(addr);
    
    var name = document.createElement('input');
    name.type = "text";
    name.value = group.name;
    cellName.appendChild(name);
    
    var desc = document.createElement('input');
    desc.type = "text";
    desc.value = group.description;
    cellDesc.appendChild(desc);
    
    var numDevices = document.createElement('input');    
    cellNumDevices.appendChild(numDevices);
    numDevices.type = "number";
    numDevices.value = group.devices.length;
    numDevices.max = 255;
    numDevices.min = 1;
    numDevices.onchange = function () {
        var deviceNames = GetDeviceNames(motors); //Create array of options to be added
        AddDevices(cellGroup, Number(numDevices.value), deviceNames, group.devices);
    };
        
    function AddDeviceSelect(deviceNames, value)
    {
        var devices = document.createElement("select");
        //Create and append the options
        for (var i = 0; i < deviceNames.length; i++) {
            var option = document.createElement("option");
            option.id = "DeviceSelect";
            option.value = deviceNames[i];
            option.text = deviceNames[i];
            devices.appendChild(option);
        }
        if (value) {
            devices.value = value;
        }
        return devices;
    }
    
    function AddDevices(cell, number, deviceNames, values)
    {
        // Clear out the row if it already exists
        if (cell) {
            while (cell.childNodes.length > number) {
                cell.removeChild(cell.lastChild);
            }
            
            for (var i = cell.childNodes.length; i < number; i++) {
                var value;
                if (values && values.length > i) {
                    value = values[i];
                }
                var devices = AddDeviceSelect(deviceNames, value);
                cell.appendChild(devices);
            }
        }
    }

    //Create and append select list
    var deviceNames = GetDeviceNames(motors); //Create array of options to be added
    AddDevices(cellGroup, Number(numDevices.value), deviceNames, group.devices);
    
    if (!(typeof newGroup === 'undefined' || newGroup === null)) {
        var add = document.createElement('input');
        add.type = "button";
        add.value = "Add";
        add.onclick = function () {
            var update = {
                address: parseInt(addr.value,16),
                name: name.value,
                description: desc.value,
                devices: []
            };
            
            for (var i = 0; i < cellGroup.childNodes.length; i++) {
                var select = cellGroup.childNodes[i].selectedIndex;
                update.devices[i] = cellGroup.childNodes[i].options[select].value;
            }
            
            $.get("AddGroup", { update: update }, function (err) {
                if (err) {
                    console.log(Date() + " AddGroup failed:");
                    console.log(err);
                }
                else {
                    AppendGroup(row, update);
                }
            });
        };
        cellControl.appendChild(add);
    }
    else {
        var update = document.createElement('input');
        update.type = "button";
        update.value = "Update";
        update.onclick = function () {
            
            var update = {
                address: parseInt(addr.value,16),
                name: name.value,
                description: desc.value,
                devices: []
            };
            
            for (var i = 0; i < cellGroup.childNodes.length; i++) {
                var select = cellGroup.childNodes[i].selectedIndex;
                update.devices[i] = cellGroup.childNodes[i].options[select].value;
            }
            
            $.get("UpdateGroup", { previous: group, update: update }, function (err) {
                if (err) {
                    console.log("UpdateDevice err:" + err);
                }
            });
        };
        cellControl.appendChild(update);
    }
    var remove = document.createElement('input');
    remove.type = "button";
    remove.value = "Delete";
    remove.onclick = function () {
        
        var remove = {
            address: parseInt(addr.value),
        };
        
        $.get("RemoveGroup", remove, function (err) {
            if (err) {
                console.log(Date() + " RemoveDevice failed:");
                console.log(err);
            }
            else {
                var table = document.getElementById("groupTable");
                table.deleteRow(row.rowIndex);
            }
        });
    };
    cellControl.appendChild(remove);
}


$(function () {
    
    $.get("GetMotors", function (serverDevices) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverDevices;
            groups = serverGroups;
            
            var deviceTable = document.getElementById("deviceTable");
            if (motors && motors.constructor === Array) {
                motors.forEach(function (motor, i) {
                    var row = deviceTable.insertRow(i + 1);
                    AppendDevice(row, motor);
                });
            }
            
            var groupTable = document.getElementById('groupTable');
            if (groups && groups.constructor === Array) {
                groups.forEach(function (group, i) {
                    var row = groupTable.insertRow(i + 1);
                    AppendGroup(row, group);
                });
            }
        });
    });
});

function AddDevice(){
    $('#deviceTable tbody').append($("#deviceTable tbody tr:last").clone());
    var table = document.getElementById("deviceTable");
    var row = table.insertRow(table.rows.length);
    AppendDevice(row, null, true);
}

function AddGroup() {
    $('#groupTable tbody').append($("#groupTable tbody tr:last").clone());
    var table = document.getElementById("groupTable");
    var row = table.insertRow(table.rows.length);
    AppendGroup(row, null, true);
}
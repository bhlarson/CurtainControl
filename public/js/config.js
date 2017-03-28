var motors;
var motors1;
var groups;

function AppendMotor(row, motor)
{
    var col = 0;
    var addr = document.createElement('input');
    addr.type = "number";
    addr.value = motor.address;
    var cell = row.insertCell(col++);
    cell.appendChild(addr);

    var name = document.createElement('input');
    name.type = "text";
    name.value = motor.name;
    var cell = row.insertCell(col++);
    cell.appendChild(name);

    var desc = document.createElement('input');
    desc.type = "text";
    desc.value = motor.description;
    var cell = row.insertCell(col++);
    cell.appendChild(desc);
    
    var type = document.createElement('input');
    type.type = "text";
    if ((typeof motor.type === 'undefined' || motor.type === null)) {
        type.value = "";
    }
    else {
        type.value = motor.type;
    }
    var cell = row.insertCell(col++);
    cell.appendChild(type);

    var date = document.createElement('input');
    date.type = "date";
    if ((typeof motor.date === 'undefined' || motor.date === null)) {
        date.value = Date()
    }
    else {
        date.value = motor.date;
    }
    var cell = row.insertCell(col++);
    cell.appendChild(date);

    var angle = document.createElement('input');
    angle.type = "number";
    if ((typeof motor.angle === 'undefined' || motor.angle === null)) {
        angle.value = 0;
    }
    else {
        angle.value = motor.angle;
    }
    var cell = row.insertCell(col++);
    cell.appendChild(angle);
    
    var distance = document.createElement('input');
    distance.type = "number";
    if ((typeof motor.distance === 'undefined' || motor.distance === null)) {
        distance.value = 0;
    }
    else {
        distance.value = motor.distance;
    }
    var cell = row.insertCell(col++);
    cell.appendChild(distance);

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

        $.get("UpdateDevice", {previous: motor, update: update}, function (res) {
            console.log("Result:" + JSON.stringify(res));
        });
    };
    var remove = document.createElement('input');
    remove.type = "button";
    remove.value = "Delete";
    var cell = row.insertCell(col++);
    cell.appendChild(update);
    cell.appendChild(remove);
}

$(function () {
    
    $.get("GetDBMotors", function (dbMotors) {
        $.get("GetMotors", function (serverMotors) {
            $.get("GetGroups", function (serverGroups) {
                console.log(dbMotors);
                motors = serverMotors;
                groups = serverGroups;
                
                var table = document.getElementById("mtable");               
                motors.forEach(function (motor, i) {
                    var row = table.insertRow(i+1);
                    AppendMotor(row, motor);
                });
                
                var table = document.getElementById('mtable');
                for (var r = 0, n = table.rows.length; r < n; r++) {
                    for (var c = 0, m = table.rows[r].cells.length; c < m; c++) {
                        //alert(table.rows[r].cells[c].innerHTML);
                    }
                }
            });
        });
    });
});

function AddMotor(){
    $('#mtable tbody').append($("#mtable tbody tr:last").clone());
}

function UpdateMotor() {
}

function DeleteMotor() {
}
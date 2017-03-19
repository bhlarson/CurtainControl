var motors;
var groups;

function AppendInput(row, value)
{
    var input = document.createElement('input');
    input.type = "text";
    input.value = motor.name;
    row.cells[j].appendChild(input);
}

function AddRow(row, motor)
{
    AppendInput(row, motor.name);
}

$(function () {
    $.get("GetMotors", function (serverMotors) {
        $.get("GetGroups", function (serverGroups) {
            motors = serverMotors;
            groups = serverGroups;
            
            var table = $('#mtable tbody');

            motors.forEach(function (motor, i) {
                var row = table.insertRow(i);
                AddRow(row, motor);
            });

            var table = document.getElementById('mtable');
            for (var r = 0, n = table.rows.length; r < n; r++) {
                for (var c = 0, m = table.rows[r].cells.length; c < m; c++) {
                    alert(table.rows[r].cells[c].innerHTML);
                }
            }
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
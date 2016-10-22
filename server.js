console.log("Starting CurtainControl on " + process.platform);

var express = require('express');
var app = express();
var http = require('http').Server(app);
var io = require('socket.io')(http);
var SolarCalc = require('solar-calc');
var schedule = require('node-schedule');
var sdn = require('./sdn-protocol');

var SerialPort;
if (process.env.NODE_ENV == 'development') {
    SerialPort = require('virtual-serialport');
}
else {
    SerialPort = require('serialport');
}

var port = process.env.port || 1337;
app.use(express.static('public'));
app.use(express.static('node_modules/jquery-ui-1.12.1'));
app.use(express.static('node_modules/socket.io/node_modules'));
app.get('/', function (req, res) {
    res.sendFile('index.html')
});

http.listen(port, function () {
    console.log('Socket.IO listening on port ' + port);
});

var solar = new SolarCalc(new Date(), 45.5, -122.8);
console.log("sunrise Today: ", solar.sunrise.toString());



//http.createServer(function (req, res) {
//    res.writeHead(200, { 'Content-Type': 'text/plain' });
//    res.end('Cutain Control\n');
//}).listen(port);
//45.5081283, -122.777942

var solar = new SolarCalc(new Date(), 45.5, -122.8);
console.log("sunrise ", solar.sunrise);

var portStr = '/dev/ttyUSB0';
if (process.platform == 'win32') {
    portStr = 'COM5';
}


var serialPort = new SerialPort(portStr, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' });

var address = 0x010201;
var stairEast = 0x0671E4;
var stairCenter = 0x067c9f;
var stairWest = 0x067121;
var overDoor = 0x065F07;
var motorAddress = overDoor;
var broadcast = 0xFFFFFF;

serialPort.on("open", function () {
    console.log('serial open');
    serialPort.on('data', function (data) {
        console.log('data received: ' + data.toString('hex'));
    });
    
    //var getPosition = sdn.GetPosition(overDoor);
    //serialPort.write(getPosition, function (err, results) {
    //    if (err != undefined) {
    //        console.log('err ' + err);
    //        console.log('results ' + results);
    //    }
    //});
    
    //var count = 0;
    //for (var i = 0; i < 10000; i++) {
    //    count = count + 1;
    //}
    /*
    console.log('DownLimit:' + motorAddress);
    var downLimit = sdn.DownLimit(motorAddress);
    serialPort.write(downLimit, function (err, results) {
        if (err != undefined) {
            console.log('err ' + err);
            console.log('results ' + results);
        }
    });
    
    var positionCmd = sdn.SetPosition(overDoor, 1000);
    serialPort.write(positionCmd, function (err, results) {
        if (err != undefined) {
            console.log('err ' + err);
            console.log('results ' + results);
        }
    });
    
    var downLimit = sdn.DownLimit(stairEast);
    serialPort.write(downLimit, function (err, results) {
        if (err != undefined) {
            console.log('err ' + err);
            console.log('results ' + results);
        }
    });
    
    var downLimit = sdn.DownLimit(stairCenter);
    serialPort.write(downLimit, function (err, results) {
        if (err != undefined) {
            console.log('err ' + err);
            console.log('results ' + results);
        }
    });
    
    //var upLimit = sdn.UpLimitGroup(address);
    //serialPort.write(upLimit, function (err, results) {
    //    if (err != undefined) {
    //        console.log('err ' + err);
    //        console.log('results ' + results);
    //    }
    //});
    
    var date = new Date();
    date.setSeconds(date.getSeconds() + 10);
    
    var j = schedule.scheduleJob(date, function () {
        var positionCmd = sdn.SetPosition(overDoor, 3500);
        serialPort.write(positionCmd, function (err, results) {
            if (err != undefined) {
                console.log('err ' + err);
                console.log('results ' + results);
            }
        });
    });
 */

    io.on('connection', function (socket) {
        socket.broadcast.emit('Server Connected');
        socket.on('disconnect', function () {
            console.log('Socket.IO  disconnected ' + socket.id);
        });
        socket.on('connect_failed', function () {
            console.log('socket.io connect_failed');
        })
        socket.on('reconnect_failed', function () {
            console.log('socket.io reconnect_failed');
        })
        socket.on('error', function (err) {
            console.log('socket.io error:' + err);
        })
        socket.on('Action', function (data) { // {cmd: direction, type:window.type, addr: window.addr}
            console.log('Action ' + JSON.stringify(data));
            if (data.cmd == 'UpLimit' && data.type == 'motor') {
                var cmd = sdn.UpLimit(data.addr);
                serialPort.write(cmd, function (err, results) {
                    if (err != undefined) {
                        console.log('err ' + err);
                        console.log('results ' + results);
                    }
                });
            }
            else if (data.cmd == 'DownLimit' && data.type == 'motor') {
                var cmd = sdn.DownLimit(data.addr);
                serialPort.write(cmd, function (err, results) {
                    if (err != undefined) {
                        console.log('err ' + err);
                        console.log('results ' + results);
                    }
                });
            }
            else if (data.cmd == 'UpLimit' && data.type == 'group') {
                var cmd = sdn.UpLimitGroup(data.addr);
                serialPort.write(cmd, function (err, results) {
                    if (err != undefined) {
                        console.log('err ' + err);
                        console.log('results ' + results);
                    }
                });
            }
            else if (data.cmd == 'DownLimit' && data.type == 'motor') {
                var cmd = sdn.DownLimitGroup(data.addr);
                serialPort.write(cmd, function (err, results) {
                    if (err != undefined) {
                        console.log('err ' + err);
                        console.log('results ' + results);
                    }
                });
            }
        })
    });
});

module.exports = app;

console.log("Starting CurtainControl on " + process.platform + " with node version " + process.version);
require('dotenv').config({ path: './config.env' });
var express = require('express')
var app = express();
var http = require('http').Server(app);
var io = require('socket.io')(http);
var SolarCalc = require('solar-calc');
var schedule = require('node-schedule');
var sdn = require('./sdn-protocol');
var curtains = require('./CurtainControl');
var mysql = require('mysql');
var log4js = require('log4js');
console.log("All External Dependancies Found");

log4js.configure({
    appenders: { command: { type: 'file', filename: 'state.log' } },
    categories: { default: { appenders: ['command'], level: 'ALL' } }
});
const cmdLog = log4js.getLogger('command');

//var init = {
//var act = curtains.ActionStr(init);
//var data = act.GetState();
//act.then(function (result){ 
//    console.log(result);
//});

// Home database credentials
var pool = mysql.createPool({
    connectionLimit: 10,
    host: process.env.dbhost,
    user: process.env.dbuser,
    //  password        : 'password',
    database: process.env.dbname
});

console.log("mysql.createPool exists=" + (typeof pool !== 'undefined'));


var port = Number(process.env.nodeport) || 1337;
app.use(express.static('public'));
app.use(express.static('node_modules/socket.io-client/dist')); // Windows
app.use(express.static('node_modules/socket.io/node_modules/socket.io-client/dist')); // Linux

app.get('/', function (req, res) {
    res.sendFile('index.html')
});

app.get('/GetMotors', function (req, res) {
    GetMotors().then(function (motors) {
        res.send(motors);
    }, function (failure) {
        res.send(failure);
    });
});

app.get('/GetGroups', function (req, res) {
    GetGroups().then(function (groups) {
        groups.forEach(function (group) {
            group.devices = JSON.parse(group.devices);
        });
        res.send(groups);
    }, function (failure) {
        res.send(failure);
    });
});

app.get('/UpdateConfig', function (req, res) {
    var previous = req.query.previous;
    var update = req.query.update;
});

app.get('/UpdateDevice', function (req, res) {
    var prevConfig = req.query.previous;
    var newConfig = req.query.update;
    var sql = 'UPDATE ' + process.env.dbdevices + ' SET ? WHERE address=' + prevConfig.address;

    pool.query(sql, [newConfig], function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

app.get('/AddDevice', function (req, res) {
    var newConfig = req.query.update;
    var sql = 'INSERT INTO ' + process.env.dbdevices + ' SET ?';

    pool.query(sql, newConfig, function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

app.get('/RemoveDevice', function (req, res) {
    var address = Number(req.query.address);
    var sql = 'DELETE FROM ' + process.env.dbdevices + ' WHERE address=?';

    pool.query(sql, address, function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

app.get('/UpdateGroup', function (req, res) {
    var prevConfig = req.query.previous;
    var newConfig = req.query.update;
    newConfig.devices = JSON.stringify(req.query.update.devices);
    var sql = 'UPDATE ' + process.env.dbgroups + ' SET ? WHERE address=' + prevConfig.address;

    pool.query(sql, [newConfig], function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

app.get('/AddGroup', function (req, res) {
    var newConfig = req.query.update;
    newConfig.devices = JSON.stringify(req.query.update.devices);
    var sql = 'INSERT INTO ' + process.env.dbgroups + ' SET ?';

    pool.query(sql, newConfig, function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

app.get('/RemoveGroup', function (req, res) {
    var address = Number(req.query.address);
    var sql = 'DELETE FROM ' + process.env.dbgroups + ' WHERE address=?';

    pool.query(sql, address, function (dberr, dbres, dbfields) {
        res.send(dberr);
    });
});

http.listen(port, function () {
    console.log('Socket.IO listening on port ' + port);
});

var solar = new SolarCalc(new Date(), 45.5, -122.8);
console.log("sunrise Today: ", solar.sunrise.toString());

var solar = new SolarCalc(new Date(), 45.5, -122.8);
console.log("sunrise ", solar.sunrise);

curtains.Initialize({ portName: process.env.serialport }).then(function (result) {
    console.log('curtains.Initialize succeeded ' + result);
}, function (err) {
    console.log('curtains.Initialize failed ' + err);
});

var broadcast = 0xFFFFFF;

io.on('connection', function (socket) {
    socket.broadcast.emit('Server Connected');
    socket.on('disconnect', function () {
        console.log('Socket.IO  disconnected ' + socket.id);
    });
    socket.on('connect_failed', function () {
        console.log('socket.io connect_failed');
    });
    socket.on('reconnect_failed', function () {
        console.log('socket.io reconnect_failed');
    });
    socket.on('error', function (err) {
        console.log('socket.io error:' + err);
    });
    socket.on('Action', function (data) { // {cmd: direction, type:window.type, addr: window.addr}
        console.log('Action ' + JSON.stringify(data));
        curtains.Start(data).then(function (result) { }, function (err) {
            console.log('curtains.Start error ' + err);
        });
    });
    socket.on('Command', function (data) { // {cmd: direction, type:window.type, addr: window.addr}
        console.log('Command ' + JSON.stringify(data));
        curtains.Start(data).then(function (result) { }, function (err) { });
    });

    curtains.Output(function (data) {
        socket.emit('Message', data);
    });
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

function GetMotors() {
    return new Promise(function (resolve, reject) {
        var connectionString = 'SELECT * FROM `' + process.env.dbdevices + '`';
        pool.query(connectionString, function (dberr, dbres, dbfields) {
            if (dberr)
                reject(dberr);
            else {
                resolve(dbres);
            }
        });
    });
}

function GetGroups() {
    return new Promise(function (resolve, reject) {
        var connectionString = 'SELECT * FROM `' + process.env.dbgroups + '`';
        pool.query(connectionString, function (dberr, dbres, dbfields) {
            if (dberr)
                reject(dberr);
            else {
                resolve(dbres);
            }
        });
    });
}

module.exports = app;
console.log("CurtainControl Started")

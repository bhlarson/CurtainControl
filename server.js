console.log("Starting CurtainControl on " + process.platform);
require('dotenv').config({ path: './config.env' });
var express = require('express');
var app = express();
var http = require('http').Server(app);
var io = require('socket.io')(http);
var SolarCalc = require('solar-calc');
var schedule = require('node-schedule');
var sdn = require('./sdn-protocol');
var curtains = require('./CurtainControl');
var mysql = require('mysql');
console.log("All External Dependancies Found");

// Home database credentials
var pool = mysql.createPool({
    connectionLimit : 10,
    host            : process.env.dbhost,
    user            : process.env.dbuser,
    //  password        : 'password',
    database        : process.env.dbname
});

console.log("mysql.createPool exists=" + (typeof pool !== 'undefined'));

//var motors = [0x0671E4, 0x067C9F, 0x067121, 0x065F07,
//    0x067944, 0x067D0E, 0x06796E, 0x067D0C, 0x067D0A, 
//    0x06794F, 0x067982, 0x067984, 0x067981,
//    0x067D0F, 0x067CD9, 0x0679D7, 0x0679D2, 0x06799B,
//    0x06792F, 0x06793F, 0x067930, 0x06793B];

//var motors = [
//    { name: "Bay East", description: "Main Bay East", address: 0x0671E4 },
//    { name: "Bay Center", description: "Main Bay South", address: 0x067C9F },
//    { name: "Bay West", description: "Main Bay West", address: 0x067121 },
//    { name: "Front Door", description: "Main Over Door", address: 0x065F07 },
//    { name: "Sunroom SE1", description: "Main Sunroom Southeast 1", address: 0x067944 },
//    { name: "Sunroom SE2", description: "Main Sunroom Southeast 2", address: 0x067D0E },
//    { name: "Sunroom SE3", description: "Main Sunroom Southeast 3", address: 0x06796E },
//    { name: "Sunroom SE4", description: "Main Sunroom Southeast 4", address: 0x067D0C },
//    { name: "Sunroom SE5", description: "Main Sunroom Southeast 5", address: 0x067D0A },
//    { name: "Sunroom SW1", description: "Main Sunroom Southwest 1", address: 0x06794F },
//    { name: "Sunroom SW2", description: "Main Sunroom Southwest 2", address: 0x067982 },
//    { name: "Sunroom SW3", description: "Main Sunroom Southwest 3", address: 0x067984 },
//    { name: "Sunroom SW4", description: "Main Sunroom Southwest 4", address: 0x067981 },
//    { name: "Bedroom SE1", description: "Basement Bedroom Southeast 1", address: 0x067D0F },
//    { name: "Bedroom SE2", description: "Basement Bedroom Southeast 2", address: 0x067CD9 },
//    { name: "Bedroom SE3", description: "Basement Bedroom Southeast 3", address: 0x0679D7 },
//    { name: "Bedroom SE4", description: "Basement Bedroom Southeast 4", address: 0x0679D2 },
//    { name: "Bedroom SE5", description: "Basement Bedroom Southeast 5", address: 0x06799B },
//    { name: "Bedroom SW1", description: "Basement Bedroom Southwest 1", address: 0x06792F },
//    { name: "Bedroom SW2", description: "Basement Bedroom Southwest 2", address: 0x06793F },
//    { name: "Bedroom SW3", description: "Basement Bedroom Southwest 3", address: 0x067930 },
//    { name: "Bedroom SW4", description: "Basement Bedroom Southwest 4", address: 0x06793B }
//];

//var groups = [
//    { name: "All Curtains", description: "All curtains", address: 0x100000,  motors:[] },
//    { name: "Main Floor", description: "All main floor curtains", address: 0x010110, motors:[] },
//    { name: "Bay Window", description: "Bay window curtains", address: 0x010202, motors:[] },
//    { name: "Front Door", description: "Front door curtains", address: 0x010203 , motors:[] },
//    { name: "All Sunroom", description: "All sunroom curtains", address: 0x010101,  motors:[] },
//    { name: "South Sunroom", description: "South sunroom curtains", address: 0x010102,  motors:[] },
//    { name: "West Sunroom", description: "West sunroom curtains", address: 0x010103,  motors:[] },
//    { name: "All Basement", description: "All basement curtains", address: 0x000101,  motors:[] },
//    { name: "South Basement", description: "South basement curtains", address: 0x000102,  motors:[] },
//    { name: "West Basement", description: "West basement curtains", address: 0x000103,  motors:[] },
//    { name: "South Corner Basement", description: "South Corner Basement curtains", address: 0x000104,  motors:[] }
//];

//var connection = mysql.createConnection({
//    host     : 'localhost',
//    user     : 'root',
//    password : 'password',
//    database : 'curtaindb'
//});

//var pool = mysql.createPool({
//    connectionLimit : 10,
//    host            : 'localhost',
//    user            : 'root',
//    password        : 'password',
//    database        : 'curtaindb'
//});

//var record = { address: 0x0671E4, name: "Bay East", description: "Main Bay East" };

//pool.query('INSERT INTO motors SET ?', record, function (err, res) {
//    if (err) throw err;
    
//    console.log('Last record insert id:', res.insertId);
//});

//pool.query('SELECT * FROM motors', function (err, res, field) {
//    if (err) {
//        exist(err); //No error
//    } else if (res) {
//        console.log(res);  //displays '[]'
//    } else {
//        console.log('pool.query no result');
//    }
//});


//var SerialPort;
//if (process.env.NODE_ENV == 'development') {
//    SerialPort = require('virtual-serialport');
//}
//else {
//    SerialPort = require('serialport');
//}

var port = process.env.PORT || 1337;
app.use(express.static('public'));
app.use(express.static('node_modules/jquery-ui-1.12.1'));
app.use(express.static('node_modules/socket.io-client/dist'));

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

app.get('/UpdateConfig', function(req, res) {
    var previous = req.query.previous;
    var update = req.query.update;
});

app.get('/UpdateDevice', function (req, res) {
    var prevConfig = req.query.previous;
    var newConfig = req.query.update;
    var sql = 'UPDATE ' + process.env.dbdevices + ' SET ? WHERE address='+prevConfig.address;
    
    pool.query(sql,[newConfig], function (dberr, dbres, dbfields) {
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

var portStr = '/dev/ttyUSB0';
if (process.platform == 'win32') {
    portStr = 'COM5';
}

//var serialPort = new SerialPort(portStr, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' });

curtains.Initialize({ portName: portStr }).then(function (result) {
    console.log('curtains.Initialize ' + result);
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
        curtains.Start(data).then(function (result) { }, function (err) { });
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
        var connectionString = 'SELECT * FROM `' + process.env.dbdevices +'`';
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
console.log("Creation  successful")

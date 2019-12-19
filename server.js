console.log("Starting CurtainControl on " + process.platform);
require('dotenv').config({ path: './config.env' });
var express = require('express');
const app = express();
const http = require('http').Server(app);
const io = require('socket.io')(http);
const sdn = require('./sdn-protocol');
const curtains = require('./CurtainControl');
const mysql = require('mysql');
var SunCalc = require('suncalc2');
var cronparser = require('cron-parser');
console.log("All External Dependancies Found");

// Home database credentials
const pool = mysql.createPool({
    connectionLimit : 10,
    host            : process.env.dbhost,
    user            : process.env.dbuser,
    //  password        : 'password',
    database        : process.env.dbname
});

console.log("mysql.createPool exists=" + (typeof pool !== 'undefined'));

function NextEvent(timestamp, schedule) {
    var events = [];
  
    var date = new Date(timestamp);
    var tomorrow = new Date(date);
    tomorrow.setDate(tomorrow.getDate() + 1);
  
    var solarToday = SunCalc.getTimes(date, process.env.latitude, process.env.longitude);
    var solarTomorrow = SunCalc.getTimes(tomorrow, process.env.latitude, process.env.longitude);
  
    var lunarToday = SunCalc.getMoonTimes(date, process.env.latitude, process.env.longitude);
    var lunarTomorrow = SunCalc.getMoonTimes(tomorrow, process.env.latitude, process.env.longitude);
  
    schedule.forEach(element => {
      var scheduledTime = 0;
      switch (element.timer) {
        case 'date':
          if (element.config.date) {
            scheduledTime = new Date(element.config.date).getTime();
          }
          break;
        case 'timestamp':
          if (element.config.timestamp) {
            scheduledTime = element.config.timestamp;
          }
          break;
        case 'chron':
          var options = {
            currentDate: new Date(timestamp),
            iterator: true
          };
          var interval = cronparser.parseExpression(element.config.expression, options);
          scheduledTime = interval.next().value.getTime();
          break;
        case 'celestial':
          if (element.config.when) {
  
            var offset = 0;
            if (element.config.offset) {
              offset = element.config.offset;
            }
  
            switch (element.config.when) {
              case 'sunrise':
                scheduledTime = solarToday.sunrise.getTime() + offset;
                if (scheduledTime < timestamp) {
                  scheduledTime = solarTomorrow.sunrise.getTime() + offset;
                }
                break;
              case 'sunset':
                scheduledTime = solarToday.sunset.getTime() + offset;
                if (scheduledTime < timestamp) {
                  scheduledTime = solarTomorrow.sunset.getTime() + offset;
                }
                break;
              // Moon events conditioned on nighttime, moon phase, and weather
              case 'moonrise':
                  scheduledTime = lunarToday.rise.getTime() + offset;
                  if (scheduledTime < timestamp) {
                    scheduledTime = lunarTomorrow.rise.getTime() + offset;
                  }
                break;
              case 'moonset':
                scheduledTime = lunarToday.set.getTime() + offset;
                if (scheduledTime < timestamp) {
                  scheduledTime = lunarTomorrow.set.getTime() + offset;
                }
                break;
            }
          }
  
          break;
      }
      var howLong = scheduledTime - timestamp;
      if(howLong >= 0){
        events.push({ts:scheduledTime, when:new Date(scheduledTime), event:element});
      }
    });
    events.sort((a, b)=>(a.ts > b.ts) ? 1 : -1); // Sort ascending
      
    return events
  }

async function ProcessEvents(curtains, state_data){
    const groups = await GetGroups();
    const allGroup = groups.find(element => element.name == "All Windows");
    const main = groups.find(element => element.name == "Main Floor");
    const bay = groups.find(element => element.name == "Bay Window");
    let up = false;

    let closeAll = () =>{
        cmd = { cmd: "DownLimit", type: "group", addr: bay.address }
        console.log(cmd);
        curtains.Start(state_data, cmd);
    }

    let openMain = () =>{
        cmd = { cmd: "UpLimit", type: "group", addr: bay.address }
        console.log(cmd);
        curtains.Start(state_data, cmd);
    }

    var schedule = [
        { timer: 'chron', config: { expression: '45 5 * * 1-5' }, condition: ()=>{return true;}, action: () => { console.log("rly1.writeSync(0)") } },
        { timer: 'chron', config: { expression: '* 7 * * 0,6' }, condition: ()=>{return true;}, action: () => { console.log("rly1.writeSync(1)") } },
        { timer: 'celestial', config: { when: 'sunrise', offset: 2*60*60 }, condition: ()=>{return true;}, action: () => { console.log("rly1.writeSync(0)") } },
        { timer: 'celestial', config: { when: 'sunset', offset: -30 * 60 }, condition: ()=>{return true;}, action: () => { console.log("rly1.writeSync(1)") } },
        { timer: 'chron', config: { expression: '03 23 * * 1-5' }, condition: ()=>{return true;}, action: () => { console.log("rly1.writeSync(0)") } },
        { timer: 'chron', config: { expression: ' */1 * * * *' }, condition: ()=>{return true;}, action: () => { if(up){openMain()} else{closeAll()} up=!up;  } },
      ];


      let promise = ms => new Promise(resolve => setTimeout(resolve, ms));

      var ts = Date.now();
      var events = NextEvent(ts, schedule);
    
      while(true){
        // Preform events that have occurred
        // Fire any timed-out events and remove them from the list
        var now;
        var fireEvents = true
        while (fireEvents) {
          now = Date.now();
          if (now >= events[0].ts) {
            if (events[0].event.condition())
              events[0].event.action();
            events.shift() // Remove completed event from list
          }
          else {
            fireEvents = false;
          }
        }
        ts = now;  // move timestamp up to last processed event
        events = NextEvent(ts, schedule);
        //console.log(JSON.stringify(events,null, 4));
        //console.log(events[0].ts-ts + ' ' + ts );
        await promise(events[0].ts-ts); 
      }

}

var port = process.env.PORT || 1337;
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

var portStr = '/dev/ttyUSB0';
if (process.platform == 'win32') {
    portStr = 'COM5';
}

//var serialPort = new SerialPort(portStr, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' });

curtains.Initialize({ portName: portStr }).then(function (state_data) {
    console.log('curtains.Initialize ' + state_data);
    ProcessEvents(curtains, state_data);
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

async function GetGroups() {
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
console.log("Curtain Control Running")

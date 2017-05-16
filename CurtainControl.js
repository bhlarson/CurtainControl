var sdn = require('./sdn-protocol');

var SerialPort;
if (process.env.NODE_ENV == 'development') {
    SerialPort = require('virtual-serialport');
}
else {
    SerialPort = require('serialport');
}

var initData = { portName: "'/dev/ttyUSB0'" };
var stateData = {serialPort: {}};

module.exports.Initialize = function (init) {
    return new Promise(function (resolve, reject) {
        initData = init;
        try {
            var serialPort = new SerialPort(initData.portName, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' , bufferSize: 4096});
            
            console.log("Serial Port " + initData.portName+ " object " + (typeof serialPort !== 'undefined'));
            
            var msg = [];
            serialPort.on('data', function (data) {
                console.log('data received: ' + data.toString('hex'));
                
                for (var i = 0; i < data.length; i++) {
                    msg.push(data[i]);
                }
                
                var parsedMsg;
                if (msg.length < 11) {
        // Still accumulating message
                }
                else {
                    parsedMsg = SerialPort.SomfyMessage(msg);
                    if (parsedMsg.err) { 
                    }
                    else if (parsedMsg.lenght) { 
                    }
                }
            });
            serialPort.on('err', function (err) {
                console.log("Serial Port " + initData.portName + " error: " + err);
            });            
            serialPort.on('open', function () {
                console.log("Serial Port opened");
                stateData.serialPort = serialPort;
                resolve("initialized");
            });
        }
        catch (err) {
            console.log("Serial Port Initialization error " + err);
            reject(err);
        }
    });
}

module.exports.CompleteEnum = {
    ACTION_STOPPED : 0x01, // Start action completed
    ACTION_COMPLETED : 0x01, // Start action completed
    ACTION_FAIL : 0x02, // Stop requested    
};



module.exports.State = function() {
    return state;
}

module.exports.Start = function (action) {
    return new Promise(function (resolve, reject) {
        var cmd, err;
        if (action.cmd == 'UpLimit' && action.type == 'motor') {
            cmd = sdn.UpLimit(Number(action.addr));
        } else if (action.cmd == 'DownLimit' && action.type == 'motor') {
            cmd = sdn.DownLimit(Number(action.addr));
        } else if (action.cmd == 'UpLimit' && action.type == 'group') {
            cmd = sdn.UpLimitGroup(Number(action.addr));
        } else if (action.cmd == 'DownLimit' && action.type == 'group') {
            cmd = sdn.DownLimitGroup(Number(action.addr));
        } else if (action.cmd == 'Percent' && action.type == 'motor') {
            cmd = sdn.SetPercent(Number(action.addr), Number(action.value));
        } else if (action.cmd == 'Jog' && action.type == 'motor') {
            cmd = sdn.Jog(Number(action.addr), action.down, Number(action.time));
        } else if (action.cmd == 'Lock' && action.type == 'motor') {
            cmd = sdn.SetLock(Number(action.addr), true);
        } else if (action.cmd == 'Unlock' && action.type == 'motor') {
            cmd = sdn.SetLock(Number(action.addr), false);
        } else {
            err = "Unknown command " + action.cmd + " type " + action.type + " address " + action.addr;
        }
        
        if (err) {
            reject({ result: ACTION_FAIL , error: err });
        } else {
            // Begin async operations
            // Prepare to receive data
            //serialPort.on('data', function (data) {
            //    console.log('data received: ' + data.toString('hex'));
            
            //    resolve(dbres);
            //});
            console.log('write ' + cmd.toString('hex'));
            serialPort.write(cmd, function (err, result) {
                if (err) {
                    console.log('write error ' + err);
                    reject({ result: ACTION_FAIL , error: err });
                }
                else {
                    console.log('write result ' + result);
                    resolve({ result: ACTION_COMPLETED });
                }
            });
        }
    });
}

module.exports.Stop = function (stopData) { }

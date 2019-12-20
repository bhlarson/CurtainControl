var log4js = require('log4js');
log4js.configure({
    appenders: { command: { type: 'file', filename: 'CurtainState.log' } },
    categories: { default: { appenders: ['command'], level: 'ALL' } }
});
const cmdLog = log4js.getLogger('command');
var sdn = require('./sdn-protocol');
var SDNPort = sdn.SP;
var initData = { portName: '/dev/ttyUSB0', log: {}};
var state = { serialPort: {}, msg: [] };

module.exports.Initialize = function (init) {
    return new Promise(function (resolve, reject) {
        initData = init;
        state.msg = new Array();
        try {
            state.serialPort = sdn.NewSP();

            var config = { log: init.log, portName: init.portName }
            state.serialPort.Start(config, function (result) {
                console.log("serialPort.Start result " + result);


var SerialPort;
if (process.env.NODE_ENV == 'development') {
    SerialPort = require('virtual-serialport');
}
else {
    SerialPort = require('serialport');
}

module.exports.initData = { portName: "'/dev/ttyUSB0'" };
module.exports.stateData = {initData: {}, serialPort: {}};

module.exports.Initialize = function (init) {
    return new Promise(function (resolve, reject) {
        var stateData = {initData: init, serialPort:{}};
        try {
            stateData.serialPort = new SerialPort(stateData.initData.portName, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' , bufferSize: 4096});
            
            console.log("Serial Port " + stateData.initData.portName+ " object " + (typeof serialPort !== 'undefined'));


            stateData.serialPort.on('data', function (data) {
                console.log('data received: ' + data.toString('hex'));
                var msg = [];
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
            stateData.serialPort.on('err', function (err) {
                console.log("Serial Port " + stateData.initData.portName + " error: " + err);
            });            
            stateData.serialPort.on('open', function () {
                console.log("Serial Port opened");
                resolve(stateData);
            });
            console.log("Serial Port " + initData.portName + " object defined:" + (typeof state.serialPort !== 'undefined'));
            resolve("initialized");
        }
        catch (err) {
            console.log("Serial Port Initialization error " + err);
            reject(stateData);
        }
    });
}

module.exports.CompleteEnum = {
    ACTION_STOPPED : 0x01, // Start action completed
    ACTION_COMPLETED : 0x01, // Start action completed
    ACTION_FAIL : 0x02, // Stop requested    
};

module.exports.Start = function (stateData, action) {
    return new Promise(function (resolve, reject) {
        var cmd, err;
        const srcAddr = 0x01;

        if (action.cmd >= sdn.CommandEnum.CTRL_MOVE && action.cmd <= sdn.CommandEnum.SET_LOCK) {
            cmd = sdn.SomfyMsg(srcAddr, action.addr, action.cmd, action.data);
            // Needs to handle the message coding, sending, complete, return data, status updates
            // Want to be able to compose sequences as well has define parent/child relationships
            // Complete for move is the move complete & data about move
            // Complete when reading data is the data received
            // Return data with complete
            // Status can be requested from action when active or complete.
            // How to map this to Node & Javascript?
            // How should different clients of the server behave?  Clients should show change of state 
            // when someone else makes changes.  For example, one person opens the curtains, others should
            // Be able to see that curtains are opening.  
            // Someone pushes the keypad, other clients should see moving and final state.  
            // This means they can get updates.  Do get updates, do they need to get the action to intepret the data?
            // I think so.  
            // How to do this?  Client sends request.  Server Starts the request and broadcast
        }
        else if (action.cmd == 'UpLimit' && action.type == 'motor') {
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
            reject({ result: module.exports.CompleteEnum.ACTION_FAIL , error: err });
        } else {
            // Begin async operations
            // Prepare to receive data
            //serialPort.on('data', function (data) {
            //    console.log('data received: ' + data.toString('hex'));
            
            //    resolve(dbres);
            //});
            console.log('write ' + cmd.toString('hex'));
            var ports = { buffer: cmd };
            state.serialPort.Input(ports)
            stateData.serialPort.write(cmd, function (err) {
                if (err) {
                    console.log('write error ' + err);
                    reject({ result: module.exports.CompleteEnum.ACTION_FAIL , error: err });
                }
                else {
                    console.log('write complete');
                    resolve({ result: module.exports.CompleteEnum.ACTION_COMPLETED });
                }
            });
        }
    });
}

module.exports.Stop = function (stopData) { }

module.exports.Output = function (dataCallback) {
    state.serialPort.Output(dataCallback);
}
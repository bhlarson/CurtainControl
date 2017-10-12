var log4js = require('log4js');
log4js.configure({
    appenders: { command: { type: 'file', filename: 'CurtainState.log' } },
    categories: { default: { appenders: ['command'], level: 'ALL' } }
});
const cmdLog = log4js.getLogger('command');

var sdn = require('./sdn-protocol');
var SDNPort = sdn.SP;
//var SerialPort;
//if (process.env.simulation == 'true' ) {
//    SerialPort = require('virtual-serialport');
//}
//else {
//    SerialPort = require('serialport');
//}


var initData = { portName: '/dev/ttyUSB0', log: {}};
var state = { serialPort: {}, msg: [] };

module.exports.Initialize = function (init) {
    return new Promise(function (resolve, reject) {
        initData = init;
        state.msg = new Array();
        try {
            //state.serialPort = new SerialPort(initData.portName, { baudrate: 4800, databits: 8, stopbits: 1, parity: 'odd' });
            state.serialPort = new SDNPort();

            //state.serialPort.Output(function (serialData) {
            //    console.log('data received: ' + data.toString('hex'));

            //    for (var i = 0; i < data.length; i++) {
            //        state.msg.push(data[i]);
            //    }

            //    var parsedMsg;
            //    if (state.msg.length < 11) {
            //        // Still accumulating message
            //    }
            //    else {
            //        parsedMsg = sdn.SomfyMessage(state.msg);
            //        if (parsedMsg.err) {
            //            console.log("Message Error: \"" + parsedMsg.err + "\".  Flush buffer");
            //            state.msg = [];
            //        }
            //        else {
            //            state.msg = state.msg.slice(parsedMsg.length, state.msg.length);
            //            console.log("Successfully parsed " + JSON.stringify(parsedMsg));
            //            console.log("Removing " + parsedMsg.length + " new length " + state.msg.length);
            //        }
            //    }
            //});

            var config = { log: init.log, portName: init.portName }
            state.serialPort.Start(config, function (result) {
                console.log("serialPort.Start result " + result);
            });
            
            console.log("Serial Port " + initData.portName + " object defined:" + (typeof state.serialPort !== 'undefined'));
            resolve("initialized");
            
        //    state.serialPort.on('data', function (data) {
        //        console.log('data received: ' + data.toString('hex'));
                
        //        for (var i = 0; i < data.length; i++) {
        //            state.msg.push(data[i]);
        //        }
                
        //        var parsedMsg;
        //        if (state.msg.length < 11) {
        //// Still accumulating message
        //        }
        //        else {
        //            parsedMsg = sdn.SomfyMessage(state.msg);
        //            if (parsedMsg.err) {
        //                console.log("Message Error: \""+ parsedMsg.err +"\".  Flush buffer");
        //                state.msg = [];
        //            }
        //            else {
        //                state.msg = state.msg.slice(parsedMsg.length, state.msg.length); 
        //                console.log("Successfully parsed " + JSON.stringify(parsedMsg));
        //                console.log("Removing " + parsedMsg.length + " new length " + state.msg.length);
        //            }
        //        }
        //    });
        //    state.serialPort.on('err', function (err) {
        //        console.log("Serial Port " + initData.portName + " error: " + err);
        //    });            
        //    state.serialPort.on('open', function () {
        //        console.log("Serial port " + initData.portName + " open");
        //        resolve("initialized");
        //    });
            resolve("initialized");
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



//module.exports.State = function() {
//    return state;
//}

//module.exports.ActionStr = function (initData) {
//    return new Promise(function (resolve, reject) {
//        init = initData;
//        state = { count: 0 };
//        result = {succeeded:false};
//        GetState = function () {
//            return state;
//        };
        
//        IntervalComplete = function () {
//            console.log("Interval alive count " + state.count);
//            if (state.count > 30) {
//                clearInterval(state.interval);
//                console.log("Action complete");
//                resolve(result);
//            };
//            state.count++;
//        };
//        state.interval = setInterval(IntervalComplete, 2000);
//    });
//}

module.exports.Start = function (action) {
    return new Promise(function (resolve, reject) {
        var cmd, err;
        const srcAddr = 0x01;

        if (action.cmd >= sdn.CommandEnum.CTRL_MOVE && action.cmd <= sdn.CommandEnum.GET_NETWORK_STAT) {
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
            //state.serialPort.write(cmd, function (err, result) {
            //    if (err) {
            //        console.log('write error ' + err);
            //        reject({ result: module.exports.CompleteEnum.ACTION_FAIL , error: err });
            //    }
            //    else {
            //        console.log('write succeeded');
            //        resolve({ result: module.exports.CompleteEnum.ACTION_COMPLETED });
            //    }
            //});
        }
    });
}

module.exports.Stop = function (stopData) { }

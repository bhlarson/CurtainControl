var log4js = require('log4js');
var SerialPort;
if (process.env.simulation == 'true') {
    SerialPort = require('virtual-serialport');
}
else {
    SerialPort = require('serialport');
}

var SP = function () {
    this.active = false;
    this.portName = '/dev/ttyUSB0';
    this.serialPort = {};
    this.message = {}
    this.timeout = 0;
    this.log = {};
    this.listeners = [];
    this.settings = { baudRate: 4800, dataBits: 8, stopBits: 1, parity: 'odd' };
    this.complete = [];
    this.writeBuffer = [];
    this.readBuffer = [];
}

SP.prototype = {

    // var initData = { log: {}, portName: '/dev/ttyUSB0'};
    Start: function (config, complete) {
        console.log("in Input");
        try {
            this.log = config.log;
            this.complete.push(complete); 
            this.serialPort = new SerialPort(config.portName, this.settings);
                this.serialPort.on('data', function (data) {
                    console.log('data received: ' + data.toString('hex'));
                    // Add data to buffer
                    for (var i = 0; i < data.length; i++) {
                        this.readBuffer.push(data[i]);
                    }
                    Evaluate();
                });
            this.serialPort.on('err', function (err) {
                var result = { err: err};
                this.complete.forEach(function callback(complete) {
                    complete(result);
                });
            pa});
            this.serialPort.on('open', function () {
            });
        }
        catch (err) {
            console.log("Serial Port Initialization error " + err);
            reject(err);
        }
    },

    Stop: function (config) {
        console.log("in Input");
        if (this.id) {
            clearTimeout(this.id);
            this.id = 0;
            var result = {};

            this.complete.forEach(function callback(complete) {
                complete(result);
            });
            
        }
    },

    // var ports = { buffer: class Buffer};
    Input: function (ports) {
        console.log("in Input");
        if (ports.buffer)
        {
            this.writeBuffer.push(ports.buffer);
        }

        //if (this.writeBuffer.length) {
        //    this.serialPort.write(ports.buffer, function (err, result) {
        //        if (err) {
        //            console.log('write error ' + err);
        //            //reject({ result: module.exports.CompleteEnum.ACTION_FAIL, error: err });
        //        }
        //        else {
        //            console.log('write succeeded');
        //            //resolve({ result: module.exports.CompleteEnum.ACTION_COMPLETED });
        //        }
        //    });

        //}
        this.Evaluate();
    },

    Output: function (listener) {
        console.log("in Output");
        this.listeners.push(listener);
    },

    RemoveOutput: function (listener) {
        console.log("in RemoveOutput");
        for (var i = this.listeners.length - 1; i >= 0; i--) {
            if (this.listeners[i] === listener) {
                this.listeners.splice(i, 1);
            }
        }
    },

    Evaluate: function () {
        console.log('in Evaluate');
        while (this.writeBuffer.length > 0) {
            var sendBuffer = this.writeBuffer.shift()
            this.serialPort.write(sendBuffer, function (err, result) {
                if (err) {
                    console.log('write error ' + err);
                    //reject({ result: module.exports.CompleteEnum.ACTION_FAIL, error: err });
                }
                else {
                    console.log('serial write ' + sendBuffer.inspect());
                }
            });
        }

        if (this.readBuffer.length)
        {
            var msgLen = this.readBuffer.length;

            // Add data to buffer
            for (var i = 0; i < data.length; i++) {
                this.readBuffer.push(data[i]);
            }

            // Send buffer to listeners
            if (this.listeners) {
                var ports = { serialData: this.msg };
                this.listeners.forEach(function (listener) {
                    listener.input(ports);
                });
            }
            this.msg.splice(0, msgLen); // Remove sent message
        }
    }
};

exports.SP = SP;

var CurtainMove = function () {
    this.id = 0;
    this.timeout = 0;
    this.log = {};
}

CurtainMove.prototype = {
    Start: function (config, complete) {
        this.log = config.log;
        if (config.timeout) {
            this.timeout = config.timeout;
        }
        this.id = setTimeout(() => {
            var result = {};
            complete(result);
        }, this.timeout)
        this.log.info(this);
    },

    Stop: function (config, complete) {
        if (this.id) {
            clearTimeout(this.id);
            this.id = 0;
            var result = {};
            complete(result);
        }
    }
};

exports.CurtainMove = CurtainMove;

module.exports.CommandEnum = {
    INVALID_COMMAD :  0x00,
    CTRL_MOVE : 0x01, // In
    CTRL_STOP : 0x02, // In
    CTRL_MOVETO : 0x03, // In
    CTRL_MOVEOF : 0x04, // In
    CTRL_WINK : 0x05, // In

    GET_MOTOR_POSITION : 0x0C, // In
    POST_MOTOR_POSITION : 0x0D,
    GET_MOTOR_STATUS : 0x0E, // In
    POST_MOTOR_STATUS : 0x0F,

    SET_MOTOR_LIMITS : 0x11, // In
    SET_MOTOR_DIRECTION : 0x12, // In
    SET_MOTOR_ROLLING_SPEED : 0x13, // In
    SET_MOTOR_IP : 0x15, // In
    POST_DCT_LOCK : 0x17,

    GET_MOTOR_LIMITS : 0x21,
    GET_MOTOR_DIRECTION : 0x22,
    GET_MOTOR_ROLLING_SPEED : 0x23,
    GET_MOTOR_IP : 0x25,
    GET_DCT_LOCK : 0x27,
    GET_FACTORY_DEFAULT : 0x2F,
    POST_MOTOR_LIMITS : 0x31,
    POST_MOTOR_DIRECTION : 0x32,
    POST_MOTOR_ROLLING_SPEED : 0x33,
    POST_MOTOR_IP : 0x35,
    POST_FACTORY_DEFAULT : 0x3F,

    GET_LOCK :  0x4B,
    SET_LOCK : 0x5B,

    GET_NODE_ADDR : 0x50,
    GET_GROUP_ADDR : 0x51,
    GET_NODE_LABEL : 0x55,
    GET_NODE_SERIAL_NUMBER : 0x5C,
    ET_NETWORK_ERROR_STAT : 0x5D,
    GET_NETWORK_STAT : 0x5E
};

const srcAddr = 0x01;

DevicesEnum = {
    ST30 : 0x02,
};

module.exports.MoveEnum = {
    DownLimit : 0x00,
	UpLimit : 0x01,
	IncPos : 0x02,
	CountPos : 0x03,
    Percent : 0x04
};
 
CheckSum = function (msg) {
        var sum = 0x0000;
        var sumSize = msg.length - 2;
        for (var i = 0; i < sumSize; i++) {
            sum += msg[i];
        }
        return sum & 0xFFFF;
};


    
module.exports.MoveData = function (move, data) {
    const m_dataSize = 4;
    const m_cmdOffset = 0;
    const m_distOffset = 1;
    
    var moveData = Buffer(m_dataSize);
    moveData[0] = move;
    moveData[1] = data & 0x00FF;
    moveData[2] = (data & 0xFF00) >> 8;
    moveData[3] = 0;
    
    return moveData;
};

module.exports.StopMotor = function (destAddr) {
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_STOP, Buffer([0x00]));
};

module.exports.StopGroup = function (groupAddr) {
    return module.exports.SomfyMsg(groupAddr, 0x0, module.exports.CommandEnum.CTRL_STOP, Buffer([0x00]));
};

module.exports.DownLimit = function (destAddr) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.DownLimit, 0);
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.DownLimitGroup = function (groupAddr) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.DownLimit, 0);
    return module.exports.SomfyMsg(groupAddr, 0x0, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.UpLimit = function (destAddr) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.UpLimit, 0);
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.UpLimitGroup = function (groupAddr) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.UpLimit, 0);
    return module.exports.SomfyMsg(groupAddr, 0x0, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.GetPosition = function (destAddr) {
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.GET_MOTOR_POSITION, Buffer(0));
};

module.exports.GetPositionGroup = function (groupAddr) {
    return module.exports.SomfyMsg(groupAddr, 0x0, module.exports.CommandEnum.GET_MOTOR_POSITION, Buffer(0));
};

module.exports.SetPosition = function (destAddr, countPosition) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.CountPos, countPosition);
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.SetPercent = function (destAddr, percent) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.Percent, percent);
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.SetPercentGroup = function (groupAddr, percent) {
    var moveData = module.exports.MoveData(module.exports.MoveEnum.Percent, percent);
    return module.exports.SomfyMsg(groupAddr, 0x0, module.exports.CommandEnum.CTRL_MOVETO, moveData);
};

module.exports.Jog = function (destAddr, down, time) {
    var jogCmd = Buffer(3);
    if (down == 'true' || down == true || down != 0) {
        jogCmd[0] = 0x00;
    }
    else {
        jogCmd[0] = 0x01;
    }

    if (time < 0.1) {
        jogCmd[1] = 0x0A;
    }
    else if (time >= 2.55) {
        jogCmd[1] = 0xff;
    }
    else {
        jogCmd[1] = time*100;
    }
    jogCmd[2] = 0x02; // slow speed
    
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.CTRL_MOVE, jogCmd);
};

module.exports.GetLock = function (destAddr) {
    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.GET_LOCK, Buffer(0));
};

module.exports.SetLock = function (destAddr, lock) {
    // 0x0000 - lock current
    // 0x0100 - lock up
    // 0x0200 - lock down
    // 0x04ip - lock at incremental position
    // 0x0500 - unlock
    var moveData = Buffer(3);
    moveData[0] = 0x05; // Unlock
    if (lock == true) {
        moveData[0] = 0x00;
    }
    moveData[1] = 0;
    moveData[2] = 1; // Priority

    return module.exports.SomfyMsg(srcAddr, destAddr, module.exports.CommandEnum.SET_LOCK, moveData);
};
    
module.exports.SomfyMsg = function (srcAddr, destAddr, cmd, msgData) {
    const msgOverhead = 11;
    const msg_offset = 0;
    const len_offset = 1;
    const dev_offst = 2;
    const src_offset = 3;
    const dest_offset = 6;
    const data_offset = 9;
    
    var dataLen = msgData.length;
    if (!dataLen) {

    }
    
    var somfyMsg = Buffer(msgOverhead + msgData.length);
    somfyMsg[msg_offset] = ~cmd;
    somfyMsg[len_offset] = ~somfyMsg.length;
    somfyMsg[dev_offst] = ~DevicesEnum.ST30;
    somfyMsg[src_offset + 2] = (srcAddr & 0x000000FF);
    somfyMsg[src_offset + 1] = ((srcAddr & 0x0000FF00) >> 8);
    somfyMsg[src_offset] = ((srcAddr & 0x00FF0000) >> 16);
    somfyMsg[dest_offset] = ~(destAddr & 0x000000FF);
    somfyMsg[dest_offset + 1] = ~((destAddr & 0x0000FF00) >> 8);
    somfyMsg[dest_offset + 2] = ~((destAddr & 0x00FF0000) >> 16);
    
    for (var i = 0; i < msgData.length; i++) {
        somfyMsg[data_offset + i] = 0xFF & ~msgData[i];
    }
    
    var checkSum = CheckSum(somfyMsg);
    somfyMsg[somfyMsg.length - 1] = (checkSum & 0x00FF);
    somfyMsg[somfyMsg.length - 2] = (checkSum & 0xFF00) >> 8;
    
    return somfyMsg;
};

function Command(id)
{
    var command = module.exports.CommandEnum.INVALID_COMMAD;
    for (var key in module.exports.CommandEnum) {
        if (module.exports.CommandEnum.hasOwnProperty(key)) {
            command = module.exports.CommandEnum[key];
        }
    }
    return command
}

function Valid(message)
{
    var valid = true;
    if (message.length > 0 && Command(0xff & ~message[0]) == module.exports.CommandEnum.INVALID_COMMAD) {
        console.log("Invalid command 0x" + Number(0xff & ~message[0]).toString(16));
        valid = false;
    }
    if (message.length > 1 && (0xFF&(~message[1])) < 11 || (0xFF & (~message[1])) > 16) {
        console.log("Invalid message length 0x" + Number(0xff & ~message[2]).toString(16));
        valid = false;
    }    
    if (message.length > 2 && (0xFF & (~message[2])) != 0x02 &&(0xFF & (~message[2])) != 0x20) {
        console.log("Invalid message unexpected resrved value 0x" + Number(0xff & ~message[1]).toString(16));
        valid = false;       
    }
    if ((0xFF & (~message[1])) >= 11 && (0xFF & (~message[1])) <= 16) {
        var expectedLen = (0xFF & (~message[1]));
        if (message.length >= expectedLen) {
            var expectedChecksum = (message[expectedLen - 2]<<8)  | message[expectedLen-1];
            // Enough data to extract message
            var cumputedCheckSum = CheckSum(message);
            if (cumputedCheckSum != expectedChecksum) {
                console.log("Invalid message checksum value 0x" + cumputedCheckSum.toString(16) + " expected 0x" + expectedChecksum.toString(16));
                valid = false;
            }
        }
    }
    else {
        console.log("Invalid message unexpected.");
        valid = false;
    }
    return valid;
}

module.exports.SomfyMessage = function (message) {
    var msg ={};
    if (!Valid(message)) {
        msg.err = "Invalid:"+ message;
        if (message.length >= 11) {
            var msgStr = "0x";
            for (var i = 0; i < message.length; i++) {
                msgStr += (message[i].toString(16));
            }
            console.log("Dumping invalid " + msgStr);

        }
        return msg;
    }
    
    var expectedLen = (0xFF & (~message[1]));
    if (message.length >= expectedLen){
        var keys = Object.keys(module.exports.CommandEnum);
        var key;
        var command = 0xFF & (~message[0]);
        msg.length = expectedLen;
        msg.command = module.exports.CommandEnum.INVALID_COMMAD;
        // Command
        for (var key in module.exports.CommandEnum) {
            if (module.exports.CommandEnum[key] == command) {
                msg.command = key;
            }
        }

        msg.src = Buffer(3);
        msg.dest = Buffer(3);
        for (var i = 0; i < 3; i++) {
            msg.src[i] = (0xFF & (~message[i + 3]));
            msg.dest[i] = (0xFF & (~message[i + 6]));
        }
        msg.data = [];
        for (var i = 0; i < expectedLen-11; i++) {
            msg.data.push(0xFF &(~message[i + 9]));
        }
    }
    return msg;
}











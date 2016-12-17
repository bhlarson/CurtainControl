module.exports.CommandEnum = {
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
        somfyMsg[data_offset + i] = ~msgData[i];
    }
    
    var checkSum = CheckSum(somfyMsg);
    somfyMsg[somfyMsg.length - 1] = (checkSum & 0x00FF);
    somfyMsg[somfyMsg.length - 2] = (checkSum & 0xFF00) >> 8;
    
    return somfyMsg;
};

function Valid(message)
{
    var valid = true;
    if (message.length() > 0 && Commnad(~message(0)) == INVALID_COMMAD) {
        valid == false;
    }
    if (message.length() > 1 && ~message(2) < 11 || ~message(2) > 16) {
        valid = false;
    }    
    if (message.length() > 2 && message(1) != 0x03 || message(1) != 0x20) {
        valid = false;       
    }
    if (message.length() > 11 && message.length() == ~message(2)) {
        var messageChecksum = message
        var cumputedCheckSum = CheckSum(message);
        if (messageChecksum != cumputedCheckSum) {
            valid = false;
        }
    }
    if (message.lenght() > 16) {
        valid = false;
    }

    return valid;
}

module.exports.SomfyReciveMessage = function (serialData, message, messageCallback) {
    message = Buffer.concat([message, serialData]);
    
    if (!Valid(message)) {
        return Buffer();
    }
    
    if (message.lenth >= msgOverhead) {
        // Might be a message.  Check 

    }

    return message;
}











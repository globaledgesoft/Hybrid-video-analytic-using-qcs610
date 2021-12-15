import boto3
import os
import time
import json
import base64 
from datetime import datetime, timedelta
import av
from PIL import Image, ImageOps, ImageDraw, ImageFont
import numpy as np
import onnxruntime as ort
from utils import predict

ort.set_default_logger_severity(3)

# Mention input and output bucket name here
IN_BUCKET = 'inbuc'
OUT_BUCKET = 'outbuc' 
STREAM_NAME = "qcs610video"

def scale(box):
    width = box[2] - box[0]
    height = box[3] - box[1]
    maximum = max(width, height)
    dx = int((maximum - width)/2)
    dy = int((maximum - height)/2)
    bboxes = [box[0] - dx, box[1] - dy, box[2] + dx, box[3] + dy]
    return bboxes

def load_model():
    s3 = boto3.client('s3')
    s3.download_file(IN_BUCKET, "version-RFB-320.onnx", "/tmp/version-RFB-320.onnx")   
    s3.download_file(IN_BUCKET, "emotion-ferplus-7.onnx", "/tmp/emotion-ferplus-7.onnx")   
    s3.download_file(IN_BUCKET, "arial.ttf", "/tmp/arial.ttf")   
    face_detector_onnx = "/tmp/version-RFB-320.onnx"
    emotion_detector_onnx = "/tmp/emotion-ferplus-7.onnx"
    face_detector = ort.InferenceSession(face_detector_onnx)
    emotion_detector = ort.InferenceSession(emotion_detector_onnx, None)
    return face_detector, emotion_detector

def emotionDetector(img,emotion_detector):
    # performing emotion detection
    emotion_table = {0:'neutral', 1:'happiness', 2:'surprise', 3:'sadness', 4:'anger', 5:'disgust', 6:'fear', 7:'contempt'}
    img = img.resize((64,64))
    img =np.asarray(img)
    img = np.moveaxis(img, -1, 0)
    img = np.reshape(img, (1, 64,64))
    img = np.expand_dims(img, axis=0).astype('float32')
    input_name = emotion_detector.get_inputs()[0].name
    output_name = emotion_detector.get_outputs()[0].name
    result = emotion_detector.run([output_name], {input_name: img})
    prediction=int(np.argmax(np.array(result).squeeze(), axis=0))
    return emotion_table[prediction]


def faceDetector(img, face_detector, threshold = 0.7 ):
    # performing ultra light weight face detection model 
    image = img.resize((320,240))
    image = np.asarray(image)
    image_mean = np.array([127, 127, 127])
    image = (image - image_mean) / 128
    image = np.transpose(image, [2, 0, 1])
    image = np.expand_dims(image, axis=0)
    image = image.astype(np.float32)
    input_name = face_detector.get_inputs()[0].name
    confidences, boxes = face_detector.run(None, {input_name: image})
    h,w  = img.size
    boxes, labels, probs = predict(h, w, confidences, boxes, threshold)
    return boxes, labels, probs



def create_video(vin,vout):
    input_ = av.open(vin)
    output = av.open(vout, 'w')
    in_stream = input_.streams.video[0]
    out_stream = output.add_stream(template=in_stream)

    for packet in input_.demux(in_stream):

        if packet.dts is None:
            continue

        packet.stream = out_stream
        output.mux(packet)

    input_.close()
    output.close()


def lambda_handler(event, context):
    # loading onnx model     
    face_detector, emotion_detector = load_model()
    kvs = boto3.client("kinesisvideo")
    endpoint = kvs.get_data_endpoint(APIName="GET_HLS_STREAMING_SESSION_URL", StreamName=STREAM_NAME)['DataEndpoint']
    kvam = boto3.client("kinesis-video-archived-media", endpoint_url=endpoint)
    s3 = boto3.client('s3')
    json_value = s3.get_object(Bucket=IN_BUCKET, Key='timestamp.json')
    timestamp = json.loads(json_value['Body'].read().decode('utf-8'))
    ST = timestamp['ST']
    ET = timestamp['ET']
    date = ST.split(' ')[0]
    time = ST.split(' ')[1].split('.')[0]    
    print(ST)
        
    url = kvam.get_hls_streaming_session_url(
        StreamName=STREAM_NAME,
        PlaybackMode='ON_DEMAND',
        HLSFragmentSelector={
            'FragmentSelectorType': 'PRODUCER_TIMESTAMP',
            'TimestampRange': {
                'StartTimestamp': ST,
                'EndTimestamp': ET
            }
        },
        DiscontinuityMode='ALWAYS',
        Expires=300, 
        MaxMediaPlaylistFragmentResults=300
    )['HLSStreamingSessionURL']
    print(url)

    create_video(url,'/tmp/vid.mp4')

    fs = open('/tmp/img.jpg', 'w+') 
    fs.close() 

    v = av.open(url)
    with v as container:
        stream = container.streams.video[0]
        ii =0  
        k = 0
        for frame in container.decode(stream):
            ii= ii + 1
            if(ii%5 != 0):
                continue
            k=k+1
            img = frame.to_image()  
            boxes, label,probs = faceDetector(img, face_detector)
            imggray = ImageOps.grayscale(img)
            print(frame)
            font = ImageFont.truetype("/tmp/arial.ttf", 52)
            for i in range(boxes.shape[0]):
                box = scale(boxes[i, :])
                img1=np.asarray(imggray)
                image = img1[box[1]:box[3],box[0]:box[2]]
                image = Image.fromarray(image) 
                value = emotionDetector(image, emotion_detector) 
                draw = ImageDraw.Draw(img)
                draw.rectangle(((box[0], box[1]), (box[2], box[3])), outline="#ff88ff", width=8)
                draw.text((box[0],box[1]), value ,"blue",font=font)
            img.save('/tmp/img.jpg',quality=80,)    
            s3.upload_file('/tmp/img.jpg', OUT_BUCKET , 'image/'+date+'/'+time+'/Image-'+str(k)+'.jpg')

    s3.upload_file('/tmp/vid.mp4', OUT_BUCKET , 'image/'+ date +'/'+time+'/video.mp4')



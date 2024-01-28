import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
import boto3
from botocore.exceptions import ClientError
from collections import Counter
import json

class Bot:

    def __init__(self, token, telegram_chat_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        #TODO how to make your bot connect with aws(done)
        region_name = os.environ['REGION']
        self.session = boto3.Session(region_name=region_name)
        self.telegram_bot_client = telebot.TeleBot(token)

        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # TODO set the webhook URL with certificate(done)
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60, certificate=open(
            'certificate.pem', 'r'))

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class ObjectDetectionBot(Bot):
    def handle_dynamo_message(self, dynamo_message):
        class_names = [label['M']['class']['S'] for label in dynamo_message['labels']]
        formatted_string = f'Objects Detected:\n'
        class_counts = Counter(class_names)
        json_string = json.dumps(class_counts)
        counts_dict = json.loads(json_string)
        for key, value in counts_dict.items():
            formatted_string += f'{key}: {value}\n'
        return formatted_string

    def get_item_by_prediction_id(self, prediction_id):
        dynamodb_client = self.session.client('dynamodb')
        dynamo_tbl = os.environ['DYNAMO_TBL']
        try:
            response = dynamodb_client.get_item(TableName=dynamo_tbl,Key={'prediction_id': {'S': prediction_id}})
            pred_summary = response.get('Item', None)
            if pred_summary:
                pred_summary = {k: list(v.values())[0] for k, v in pred_summary.items()}
                return pred_summary
            else:
                print(f"No item found with prediction_id: {prediction_id}")
                return None
        except Exception as e:
            print(f"Error fetching item from DynamoDB: {e}")
            return None

    def send_message_to_sqs(self, msg_body):
        sqs_client = self.session.client('sqs')
        queue_url = os.environ['QUEUE_URL']
        try:
            response = sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=msg_body
            )
            logger.info(response)
        except ClientError as e:
            print(f"An error occurred: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    def upload_to_s3(self, file_path, bucket_name, object_name=None):
        if object_name is None:
            object_name = os.path.basename(file_path)

        s3_client = self.session.client('s3')
        try:
            s3_client.upload_file(file_path, bucket_name, object_name)
        except ClientError as e:
            logger.error(e)
            return False
        return True
    def download_pred_photo_s3(self,bucket_name,s3_photo_path, local_path):
        s3_client = self.session.client('s3')
        try:
            s3_client.download_file(bucket_name, s3_photo_path, local_path)
            logger.info(f'downloaded successfully to {local_path}')
        except Exception as e:
            logger.error(f'Error downloading image from S3:{e}')
            return None
        return local_path
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        if self.is_current_msg_photo(msg):
            photo_path = self.download_user_photo(msg)
            # TODO upload the photo to S3(done)
            bucket = os.environ['BUCKET_NAME']
            self.upload_to_s3(photo_path,bucket,photo_path)
            # TODO send a job to the SQS queue(done)
            self.send_message_to_sqs(f"{photo_path},{msg['chat']['id']}")
            # TODO send message to the Telegram end-user (e.g. Your image is being processed. Please wait...)(done)
            self.send_text(msg['chat']['id'], f'Your image is being processed. Please wait...')
        elif "text" in msg:
            content_msg = msg['text']
            self.send_text(msg['chat']['id'], f'Your original message: {content_msg}\n send me a photo')
        else:
            self.send_text(msg['chat']['id'], "i don't know how to handle this  \n send me a photo")
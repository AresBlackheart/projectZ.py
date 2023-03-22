from .utils import exceptions, objects
from .utils.generator import Generator
from .utils.headers import Headers
from .async_socket import AsyncSocket, AsyncCallBacks

from json import dumps, loads
from sys import maxsize
from random import randint
from aiohttp import ClientSession, MultipartWriter
from asyncio import get_event_loop, new_event_loop, create_task
from magic import from_buffer
from io import BytesIO
from aiofiles.threadpool.binary import AsyncBufferedReader
from typing import Union, Optional

gen = Generator()

class AsyncClient(AsyncSocket, AsyncCallBacks):
	def __init__(self, deviceId: str = None, socket_debug: bool = False, language: str = "en-US", country_code: str = "en", time_zone: int = 180):
		self.api = 'https://api.projz.com'
		self.deviceId = deviceId if deviceId else gen.deviceId()
		self.profile = objects.User()
		self.language = language
		self.country_code = country_code
		self.time_zone = time_zone

		self.session = ClientSession()

		AsyncSocket.__init__(self, headers=self.parse_headers, debug=socket_debug)
		AsyncCallBacks.__init__(self)


	def __del__(self):
		try:
			loop = get_event_loop()
			loop.run_until_complete(self.close_session())
		except RuntimeError:
			loop = new_event_loop()
			loop.run_until_complete(self.close_session())

	async def close_session(self):
		if not self.session.closed: await self.session.close()



	def parse_headers(self, endpoint: str, data = None, content_type: str = 'application/json') -> dict:
		h = Headers(deviceId=self.deviceId, sid=self.profile.sid, time_zone=self.time_zone, country_code=self.country_code, language=self.language)
		head = h.get_persistent_headers()
		head.update(h.Headers())
		head.update({"Content-Type": content_type} if content_type else {})
		head["HJTRFS"] = gen.signature(path=endpoint, headers=head, body=data or bytes())
		return head


	async def upload_media(self, file: AsyncBufferedReader, target: int = 1, returnType: str = 'object', duration: int = 0):

		file_content = await file.read()
		content = BytesIO()
		writer = MultipartWriter()
		part = writer.append(file_content, {"Content-Type": from_buffer(file_content, mime=True)})
		part.set_content_disposition("form-data", name="media", filename=file.name)
		await writer.write(objects.CopyToBufferWriter(content))
		endpoint = f"/v1/media/upload?target={target}&duration={duration}"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, content_type=f"multipart/form-data; boundary={writer.boundary}", data=content.getvalue()), data=content.getvalue()) as response:
			if response.status != 200:return exceptions.CheckException(await response.text())
			else:
				return objects.Media(loads(await response.text())) if returnType == 'object' else loads(await response.text())


	async def login(self, email: str, password: str):

		data = dumps({
			"authType": 1,
			"email": email,
			"password": password
		})
		endpoint = '/v1/auth/login'

		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			if response.status != 200: return exceptions.CheckException(await response.text())
			else:
				self.profile = objects.User(loads(await response.text()))
				await self.connect()
				return self.profile


	async def logout(self):
		endpoint = '/v1/auth/logout'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			if response.status != 200: return exceptions.CheckException(await response.text())
			else:
				self.profile = objects.User()
				await self.disconnect()
				return response.status

	async def Online(self):
		if self.online_loop_active: return
		self.online_loop_active = create_task(self.online_loop())
		return self.online_loop_active

	async def Offline(self):
		if self.online_loop_active:
			self.online_loop_active.cancel()
			self.online_loop_active = None
		return self.online_loop_active


	async def join_chat(self, chatId: int) -> None:

		endpoint = f'/v1/chat/threads/{chatId}/members'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status



	async def leave_chat(self, chatId: int) -> None:

		endpoint = f'/v1/chat/threads/{chatId}/members'
		async with self.session.delete(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def get_from_link(self, link: str):

		data = dumps({"link": link})
		endpoint = f"/v1/links/path"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else objects.FromLink(loads(await response.text()))


	async def get_link(self, userId: int):

		data = dumps({
			"objectId": 0,
			"objectType": 0,
			"parentId": 0,
			"path": f"user/{userId}",
			"circleIdForCircleAnnouncement": 0,
			"parentType": 0
		})

		endpoint = '/v1/links/share'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else objects.FromLink(loads(await response.text()))

	async def get_my_chats(self, start: int = 0, size: int = 20, type: str = 'managed'):

		endpoint = f'/v1/chat/joined-threads?start={start}&size={size}&type={type}'
		async with self.session.get(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else  objects.Thread(loads(await response.text()))


	async def send_message(self, chatId: int, message: str = None, file: AsyncBufferedReader = None, message_type: int = 1, reply_to: int = None, poll_id: int = None, dice_id: int = None): 
		data = {
			"threadId": chatId,
			"uid": self.profile.uid,
			"seqId": randint(0, maxsize),
			"extensions": {}
		}
		if message:
			data["content"]=message
			data["type"]=message_type
		elif file:
			data["type"]=2
			data["media"] = await self.upload_media(file=file, target=8, returnType='dict')
		else:
			raise exceptions.WrongType('Specify the "message" or "file" argument')

		if reply_to: data["extensions"]["replyMessage"] = reply_to
		if poll_id: data["extensions"]["pollId"] = poll_id
		if dice_id: data["extensions"]["diceId"] = dice_id

		resp = await self.send(t=1, data=data, threadId=chatId)
		return resp



	async def send_verify_code(self, email: str, country_code: str = None):
		data = dumps({
			"authType": 1,
			"purpose": 1,
			"email": email,
			"password": "",
			"phoneNumber": "",
			"securityCode": "",
			"invitationCode": "",
			"secret": "",
			"gender": 0,
			"birthday": "1990-01-01",
			"requestToBeReactivated": False,
			"countryCode": country_code if country_code else self.country_code,
			"suggestedCountryCode": country_code.upper() if country_code else self.country_code.upper(),
			"ignoresDisabled": True,
			"rawDeviceIdThree": gen.generate_device_id_three()
		})
		
		endpoint = '/v1/auth/request-security-validation'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status

	async def register(self, email: str, password: str, code: str, icon: Union[AsyncBufferedReader, objects.Media], country_code: str = None, invitation_code: str = None, nickname: str = 'XsarzyBest', tag_line: str = 'projectZ', gender: int = 100, birthday: str = '1990-01-01'):
		data = dumps({
			"authType": 1,
			"purpose": 1,
			"email": email,
			"password": password,
			"securityCode": code,
			"invitationCode": invitation_code or "",
			"nickname": nickname,
			"tagLine": tag_line,
			"icon": icon.json if isinstance(icon, objects.Media) else await self.upload_media(icon, returnType='dict'),
			"nameCardBackground": None,
			"gender": gender,
			"birthday": birthday,
			"requestToBeReactivated": False,
			"countryCode": country_code if country_code else self.country_code,
			"suggestedCountryCode": country_code.upper() if country_code else self.country_code.upper(),
			"ignoresDisabled": True,
			"rawDeviceIdThree": gen.generate_device_id_three()
		})

		endpoint = '/v1/auth/register'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def visit(self, userId):

		endpoint = f'/v1/users/profile/{userId}/visit'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def add_to_favorites(self, userId: Union[list, int]):

		userIds = userId if isinstance(userId, list) else [userId]
		data = dumps({"targetUids": userIds})
		endpoint = '/v1/users/membership/favorites'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def report(self, userId: int, message: str, images: Union[AsyncBufferedReader, list[AsyncBufferedReader]], flagType: int = 100):

		media = list()
		if isinstance(images, AsyncBufferedReader):images=[images]
		elif isinstance(images, list):pass
		else:raise exceptions.WrongType()
		data = {
			"objectId": userId,
			"objectType": 4,
			"flagType": flagType,
			"message": message,
		}
		for image in images:
			media.append(await self.upload_media(image, returnType='dict'))
		data["mediaList"] = media


		data = dumps(data)
		endpoint = f'/v1/flags'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def delete_message(self, chatId: int, messageId: int):

		endpoint = f'/v1/chat/threads/{chatId}/messages/{messageId}'
		async with self.session.delete(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status

	async def kick(self, chatId: int, userId: int, denyEntry: bool = False, removeContent: bool = False):
		
		endpoint = f"/v1/chat/threads/{chatId}/members/{userId}?block={str(denyEntry).lower()}&removeContent={str(removeContent).lower()}"
		async with self.session.delete(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def pin_chat(self, chatId):

		endpoint = f'/v1/chat/threads/{chatId}/pin'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status

	async def apply_bubble(self, chatId: int, bubbleColor: str):

		data = dumps({"threadId": chatId, "bubbleColor": bubbleColor})
		endpoint = f'/v1/chat/apply-bubble'
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def invite_to_co_host(self, chatId: int, userId: Union[list, int]):
		#TODO
		if isinstance(userId, int): userIds = [userId]
		elif isinstance(userId, list): userIds = userId
		else:raise exceptions.WrongType('Specify the "message" or "file" argument')
		data = dumps({"coHostUids": userIds})
		endpoint = f"/v1/chat/threads/{chatId}/invite-co-host"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def invite_to_host(self, chatId: int, userId: int):
		#TODO
		endpoint = f"/v1/chat/threads/{chatId}/invite-host/{userId}"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def accept_co_host(self, chatId: int):

		endpoint = f"/v1/chat/threads/{chatId}/accept-as-co-host"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def accept_host(self, chatId: int):
		
		endpoint = f"/v1/chat/threads/{chatId}/accept-as-host"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def auto_offline(self, chatId: int, switch: bool = False):

		endpoint = f"/v1/chat/threads/{chatId}/auto-offline/{'disable' if switch == False else 'enable'}"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def check_in(self):
		endpoint = f"/v1/users/check-in"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			response = exceptions.CheckException(await response.text()) if response.status != 200 else loads(await response.text())
		orderId = response.get("orderId", None)

		await self.claim_transfer_orders(orderId=orderId)

		return response

	async def claim_transfer_orders(self, orderId: int):

		endpoint = f"/biz/v3/transfer-orders/{orderId}/claim"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def claim_gift_boxes(self, orderId: int):
		endpoint = f"/v1/gift-boxes/{orderId}/claim"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else response.status


	async def get_transfer_order_info(self, orderId: int):

		endpoint = f"/biz/v1/transfer-orders/{orderId}"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint)) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else loads(await response.text())

	async def send_coins(self, wallet_password: int, userId: int, amount: int, title: str = "Всего Наилучшего!"):

		data = dumps({
			"toObjectId": userId,
			"amount": f"{amount}000000000000000000",
			"paymentPassword": str(wallet_password),
			"toObjectType": 4,
			"currencyType": 100,
			"title": title
		})

		endpoint = f"/biz/v1/gift-boxes"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else loads(await response.text())


	async def online_chat_status(self, chatId: int, online: bool = True):

		data = dumps({"partyOnlineStatus": 1 if online else 2})
		endpoint = f"/v1/chat/threads/{chatId}/party-online-status"
		async with self.session.post(f"{self.api}{endpoint}", headers=self.parse_headers(endpoint=endpoint, data=data), data=data) as response:
			return exceptions.CheckException(await response.text()) if response.status != 200 else loads(await response.text())
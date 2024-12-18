# encoding:utf-8
import os
import json
import base64
import requests
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *

@plugins.register(
    name="Img2Url",
    desire_priority=200,
    hidden=False,
    desc="图片转链接插件",
    version="1.0",
    author="Lingyuzhou",
)
class Img2Url(Plugin):
    def __init__(self):
        super().__init__()
        # 加载配置
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.imgbb_api_key = config.get("imgbb_api_key", "")
        except Exception as e:
            logger.error(f"[Img2Url] 加载配置文件失败: {e}")
            self.imgbb_api_key = None

        if not self.imgbb_api_key:
            logger.error("[Img2Url] 请在config.json中配置imgbb_api_key")
            
        # 设置触发词和状态标记
        self.trigger_word = "图转链接"
        self.waiting_for_image = {}
        
        # 注册消息处理器
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[Img2Url] 插件初始化成功")

    def upload_to_imgbb(self, base64_image: str) -> str:
        """上传base64图片到ImgBB"""
        try:
            data = {
                'key': self.imgbb_api_key,
                'image': base64_image
            }
            
            response = requests.post(
                'https://api.imgbb.com/1/upload',
                data=data
            )
            
            if response.status_code == 200:
                result = response.json()
                if result['success']:
                    logger.info("[Img2Url] 图片上传到ImgBB成功")
                    return result['data']['url']
                else:
                    logger.error(f"[Img2Url] 上传到ImgBB失败: {result.get('error', {}).get('message', '未知错误')}")
            else:
                logger.error(f"[Img2Url] 上传到ImgBB请求失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"[Img2Url] 上传到ImgBB时发生错误: {e}")
        return None

    def get_image_data(self, msg, content):
        """获取图片数据的辅助函数"""
        try:
            # 打印调试信息
            logger.debug(f"[Img2Url] 消息类型: {type(content)}")
            logger.debug(f"[Img2Url] 消息内容: {content[:100] if isinstance(content, str) else '二进制数据'}")
            logger.debug(f"[Img2Url] 消息属性: {dir(msg)}")

            # 1. 尝试从原始消息的download方法获取
            if hasattr(msg, '_rawmsg') and hasattr(msg._rawmsg, 'download'):
                logger.debug("[Img2Url] 尝试使用_rawmsg.download方法获取图片")
                try:
                    # 获取文件名
                    file_name = msg._rawmsg.get('FileName', 'temp.png')
                    # 创建临时文件路径
                    temp_path = os.path.join(os.getcwd(), 'tmp', file_name)
                    # 下载图片
                    msg._rawmsg.download(temp_path)
                    
                    if os.path.exists(temp_path):
                        with open(temp_path, 'rb') as f:
                            image_data = f.read()
                        # 删除临时文件
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                        logger.debug("[Img2Url] 成功从_rawmsg.download获   图片数据")
                        return base64.b64encode(image_data).decode('utf-8')
                except Exception as e:
                    logger.warning(f"[Img2Url] 使用_rawmsg.download获取图片失败: {e}")

            # 2. 尝试从Content获取图片数据
            if hasattr(msg, '_rawmsg') and 'Content' in msg._rawmsg:
                try:
                    content_data = msg._rawmsg['Content']
                    if isinstance(content_data, str) and len(content_data) > 0:
                        # 尝试解码Content数据
                        try:
                            image_data = base64.b64decode(content_data)
                            logger.debug("[Img2Url] 成功从Content解码图片数据")
                            return base64.b64encode(image_data).decode('utf-8')
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"[Img2Url] 从Content获取图片数据失败: {e}")

            # 3. 尝试从Text属性获取
            if hasattr(msg, '_rawmsg') and 'Text' in msg._rawmsg:
                try:
                    text_fn = msg._rawmsg['Text']
                    if callable(text_fn):
                        # 创建临时文件路径
                        temp_path = os.path.join(os.getcwd(), 'tmp', 'temp.png')
                        # 调用Text函数下载图片
                        text_fn(temp_path)
                        
                        if os.path.exists(temp_path):
                            with open(temp_path, 'rb') as f:
                                image_data = f.read()
                            # 删除临时文件
                            try:
                                os.remove(temp_path)
                            except:
                                pass
                            logger.debug("[Img2Url] 成功从Text函数获取图片数据")
                            return base64.b64encode(image_data).decode('utf-8')
                except Exception as e:
                    logger.warning(f"[Img2Url] 从Text获取图片数据失败: {e}")

            # 如果所有方法都失败，打印更多调试信息
            logger.error("[Img2Url] 所有获取图片数据的方法都失败了")
            if hasattr(msg, '_rawmsg'):
                logger.debug(f"[Img2Url] 原始消息属性: {dir(msg._rawmsg)}")
                logger.debug(f"[Img2Url] 原始消息内容: {msg._rawmsg}")
            
            return None

        except Exception as e:
            logger.error(f"[Img2Url] 获取图片数据时发生错误: {e}")
            return None

    def on_handle_context(self, e_context: EventContext):
        """处理消息"""
        content = e_context['context'].content
        msg = e_context['context']['msg']
        
        if not msg.from_user_id:
            return
            
        # 处理文本消息中的触发词
        if e_context['context'].type == ContextType.TEXT and self.trigger_word in content:
            self.waiting_for_image[msg.from_user_id] = True
            e_context['reply'] = Reply(ReplyType.TEXT, "请发送需要转换的图片")
            e_context.action = EventAction.BREAK_PASS
            return
            
        # 处理图片消息
        if e_context['context'].type == ContextType.IMAGE and msg.from_user_id in self.waiting_for_image:
            try:
                logger.debug(f"[Img2Url] 开始处理图片消息: {msg}")
                
                # 获取图片数据
                base64_data = self.get_image_data(msg, content)
                if not base64_data:
                    logger.error("[Img2Url] 无法获取图片数据")
                    e_context['reply'] = Reply(ReplyType.ERROR, "无法获取图片数据，请重试")
                    return

                logger.debug("[Img2Url] 成功获取图片数据，准备上传")
                
                # 上传图片获取URL
                image_url = self.upload_to_imgbb(base64_data)
                if not image_url:
                    e_context['reply'] = Reply(ReplyType.ERROR, "上传图片失败")
                    return
                
                # 使用自定义格式返回图片URL
                url_text = f"====== 图片上传成功 ======\n链接: {image_url}\n====================="
                
                # 创建回复对象，不使用kwargs
                reply = Reply(ReplyType.TEXT, url_text)
                e_context['reply'] = reply
                
                # 设置上下文参数来防止图片解析
                e_context['context'].kwargs['no_image_parse'] = True
                e_context.action = EventAction.BREAK_PASS
                
                # 清除等待状态
                del self.waiting_for_image[msg.from_user_id]
                
            except Exception as e:
                logger.error(f"[Img2Url] 处理图片时发生错误: {e}")
                e_context['reply'] = Reply(ReplyType.ERROR, f"处理图片时发生错误: {e}")

    def get_help_text(self, **kwargs):
        help_text = "图片转链接插件使用说明：\n"
        help_text += "1. 发送'图转链接'，收到反馈消息后再发送图片\n"
        help_text += "2. 插件会自动上传图片并返回可访问的URL\n"
        return help_text
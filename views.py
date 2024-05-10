import os
from telethon import Button
from telethon.types import User

from language import lang_handler
from database import database

class View:
    def __init__(self, *buttons: str, ignore_adm: bool = False) -> None:
        self.phrases = buttons
        self.ignore_adm = ignore_adm

    def __call__(self, user_entity: User, ignore_adm: bool = False, ignore: list[str] = []) -> list[Button]:
        if any([i is None for i in self.phrases]):
            return Button.clear()
        
        markup = []
        temp = []
        for i in self.phrases:
            if i in ignore:
                continue
            if i == '':
                markup.append(temp)
                temp = []
            else:
                temp.append(Button.text(lang_handler.get_phrase_by_key(user_entity, i), resize=True))
        markup.append(temp)

        if user_entity.id in database.admins.values() and not self.ignore_adm and\
                not ignore_adm: # Админская(-ие) кнопка(-и), хендлится отдельно
            markup.append([Button.text('Админ панель', resize=True)])

        return markup


class InlineView:
    def __init__(self, *buttons: tuple[str, str]) -> None:
        self.phrases = buttons

    def __call__(self, user_entity: User) -> list[Button]:
        return [
            [Button.inline(lang_handler.get_phrase_by_key(user_entity, key), data)]
            for key, data in self.phrases
        ]


class AdminView:
    phrases = [['Проверить задания'], ['Массовая рассылка'], ['Метрики']]

    def __call__(self):
        return [[Button.text(j, resize=True) for j in i] for i in self.phrases]


clear = View(None)
main = View('balance', 'wallet', '', 'terms', 'settings', '', 'info')
settings = View('back', ignore_adm=True)
tasks = View('sn_insta', 'sn_tiktok', '', 'sn_telegram', 'sn_vk', '', 'sn_other')

LANGUAGES = {
    'Русский🇷🇺': 'lang_ru',
    'English🇺🇸': 'lang_en'
}
langs = [Button.inline(text, data) for text, data in LANGUAGES.items()]
awards = InlineView(('awards', 'awards'))
channels = lambda user: [[Button.url(lang_handler.get_phrase_by_key(user, text), 
                                    url)]
                                    for text, url 
                                    in zip(['sub_channel_1', 'sub_channel_2'], 
                                           os.getenv('SUB_CHANNELS').split(','))
                        ]
info = InlineView(('tokenomics', 'tokenomics'), ('contacts', 'contacts'), 
                  ('social_networks', 'social_networks'), ('user_agreement', 'user_agreement'))

admin = AdminView()
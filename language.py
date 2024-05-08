import json
import hjson
import pathlib

from telethon.types import User
from database import DBUser

AVAILABLE_LANGUAGES = [i.stem for i in  pathlib.Path('languages/').glob('*.hjson')]


class LanguageHandler:
    def __init__(self, base_path: str) -> None:
        data = {i: {} for i in AVAILABLE_LANGUAGES}
        for lang in AVAILABLE_LANGUAGES:
            with open(f'{base_path}{lang}.hjson', 'r') as f:
                _json = hjson.load(f)
                for key, val in _json.items():
                    data[lang][key] = val

        self.data = data

    def get_language(self, user_entity: User) -> str:
        user = DBUser.fromUserEntity(user_entity)  # Lang is always defined in DBUser
        if user is None:
            return user_entity.lang_code if user_entity.lang_code in AVAILABLE_LANGUAGES else 'ru'
        
        return user.language

    def get_key_by_phrase(self, user_entity: User, phrase: str) -> str:
        lang = self.get_language(user_entity)
        for key, val in self.data[lang].items():
            if val == phrase:
                return key

        return None

    def get_phrase_by_key(self, user_entity: User, phrase: str) -> str:
        return self.data[self.get_language(user_entity)].get(phrase, '')


lang_handler = LanguageHandler('languages/')
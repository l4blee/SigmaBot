import hjson
import pathlib

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

    def get_language(self, db_user: DBUser) -> str:  # Lang is always defined in DBUser
        if db_user is None:
            return 'ru'
        
        return db_user.language

    def get_key_by_phrase(self, db_user: DBUser, phrase: str) -> str:
        lang = self.get_language(db_user)
        for key, val in self.data[lang].items():
            if val == phrase:
                return key

        return None

    def get_phrase_by_key(self, db_user: DBUser, phrase: str) -> str:
        return self.data[self.get_language(db_user)].get(phrase, '')


lang_handler = LanguageHandler('languages/')
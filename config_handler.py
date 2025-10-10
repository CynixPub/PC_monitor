import configparser
import os
from utils import user_data_path

class ConfigHandler:
    def __init__(self, config_file='config.conf'):
        self.config_file = user_data_path(config_file)
        self.config = configparser.ConfigParser()
        self._load_config()

    def _create_default_config(self):
        """创建或覆盖为默认配置文件"""
        self.config['SERIAL'] = {'COM': 'COM5'}
        with open(self.config_file, 'w') as f:
            self.config.write(f)
        print(f"已创建/重置为默认配置: {self.config_file}")

    def _load_config(self):
        """加载或创建配置文件"""
        if not os.path.exists(self.config_file):
            self._create_default_config()
        else:
            try:
                read_ok = self.config.read(self.config_file)
                if not read_ok:
                    raise ValueError("配置文件为空。")
                if 'SERIAL' not in self.config or 'COM' not in self.config['SERIAL']:
                    raise configparser.NoSectionError('SERIAL or COM key missing')
                print(f"已加载配置: {self.config_file}")
            except (configparser.Error, ValueError) as e:
                print(f"配置文件 '{self.config_file}' 格式错误或不完整: {e}。将使用默认配置重建。")
                self._create_default_config()

    def get_com_port(self) -> str:
        """获取 COM 端口号"""
        try:
            return self.config.get('SERIAL', 'COM').strip("'\"")
        except (configparser.NoSectionError, configparser.NoOptionError):
            # 如果配置丢失，返回默认值并重新生成配置
            self._create_default_config()
            return self.config.get('SERIAL', 'COM').strip("'\"")

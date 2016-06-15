import shutil
import os
from urllib.request import urlretrieve

# This is a dirty update script that I'm just writing for the ease of updating
#   files right now. I might write a better one later.

directory = __file__[:__file__.rindex('/')]
print("In directory {}".format(directory))

print("Making a backup...")
backup_directory = directory + '/temp/jshbot_update_backup.zip'
try:
    os.remove('~/jshbot_update_backup.zip')
except:
    pass
try:
    os.remove(backup_directory)
except:
    pass
shutil.make_archive('~/jshbot_update_backup', 'zip', directory)
shutil.move('~/jshbot_update_backup.zip', backup_directory)
print("Backup made at " + backup_directory + "\n")

print("Downloading files...")
url = 'https://github.com/jkchen2/JshBot/archive/master.zip'
urlretrieve(url, directory + '/temp/core_update.zip')
url = 'https://github.com/jkchen2/JshBot-plugins/archive/master.zip'
urlretrieve(url, directory + '/temp/plugins_update.zip')
print("Finished downloading files.\n")

print("Unpacking...")
shutil.unpack_archive(
    directory + '/temp/core_update.zip', directory + '/temp/update')
shutil.unpack_archive(
    directory + '/temp/plugins_update.zip', directory + '/temp/update')
print("Unpacked.\n")

print("Updating the core...")
try:
    shutil.rmtree(directory + '/jshbot')
except:
    pass
current_directory = directory + '/temp/update/JshBot-master/'
shutil.move(current_directory + 'jshbot', directory + '/')
shutil.copy2(
    current_directory + 'config/base-manual.json',
    directory + '/config/base-manual.json')
print("Updated the core.\n")

print("Updating plugins...")
current_directory = directory + '/temp/update/JshBot-plugins-master/'
for plugin in os.listdir(directory + '/plugins'):
    if plugin.endswith('.py') and not plugin.startswith((',', '_')):
        copy_directory = directory + '/plugins/'
        config_directory = directory + '/config/'
        from_directory = current_directory + plugin[:-3] + '/'
        for update_file in os.listdir(from_directory):
            if update_file.endswith('.py'):
                shutil.copy2(from_directory + update_file, copy_directory)
            elif (update_file.endswith('manual.json') or
                    not os.path.isfile(config_directory + update_file)):
                shutil.copy2(from_directory + update_file, config_directory)

        print("Updated " + plugin[:-3])

print("\nFinished update.")

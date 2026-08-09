[app]

# (str) Title of your application
title = Word Chain

# (str) Package name
package.name = wordgame

# (str) Package domain (needed for android packaging)
package.domain = org.wordgame

# (str) Source directory where the application files are located
source.dir = .

# (list) Source files to include (let it include python and json/images if any)
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application versioning
version = 0.1

# (list) Application requirements
# pyjnius যুক্ত করা হয়েছে এবং pyaudio পুরোপুরি বাদ দেওয়া হয়েছে
requirements = python3,kivy,requests,urllib3,certifi,websocket-client,pyjnius

# (str) Supported orientations
orientation = portrait

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support.
android.minAPI = 21

# (str) Android architectural build types
android.archs = armeabi-v7a

# (str) Android NDK version to use
android.ndk = 25b

# (str) Android permissions
android.permissions = GET_ACCOUNTS, INTERNET, ACCESS_NETWORK_STATE, RECORD_AUDIO

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

from pecan import expose, request, Response
from webob.exc import status_map
from shelljob import proc
import random, string, os, json

def istext(file):
    s=file.read(512)
    file.seek(0)
    text_characters = "".join(map(chr, range(32, 127)) + list("\n\r\t\b"))
    _null_trans = string.maketrans("", "")
    if not s:
        return True
    if "\0" in s:
        return False
    t = s.translate(_null_trans, text_characters)
    if float(len(t))/float(len(s)) > 0.10:
        return False
    return True

class RootController(object):

  @expose(content_type='text/event-stream')
  def puppet(self):
    g = proc.Group()
    p = g.run(["python", "-u", "test/output.py"])
    def read_process():
      while g.is_pending():
        lines = g.readlines()
        for proc, line in lines:
          yield line 
    return Response(content_type='text/event-stream',
                    app_iter=read_process())

  @expose(generic=True, template='index.html')
  def index(self):
    return dict()

  @index.when(method='POST', template='final.html')
  def index_post(self, **kwargs):

    temp = dict(keyfallback = False, kwargs=kwargs) 

    password_length = 32
    password_chars = string.ascii_letters + string.digits + '!@#$%^&*()'
    password = ''.join([random.choice(password_chars) for n in xrange(password_length)])
    path = "/opt/puppet/hieradata/"
    filename = "workroom.json"

    config = {
      "system::hostname":               kwargs['hostname'],
      "st2::auth":                      True,
      "st2::api_url":                   "https://%s:9101" % kwargs['hostname'],
      "st2::auth_url":                  "https://%s:9100" % kwargs['hostname'],
      "st2::cli_api_url":               "https://%s:9101" % kwargs['hostname'],
      "st2::cli_auth_url":              "https://%s:9100" % kwargs['hostname'],
      "st2::cli_username":              "admin",
      "st2::cli_password":              kwargs['password-1'],
      "st2::stanley::username":         kwargs['username'],
      "st2::stanley::password":         password,
      "st2::stanley::ssh_private_key":  kwargs['integrationacct'],

      "hubot::chat_alias": "!",
      "hubot::env_export": {
        "HUBOT_LOG_LEVEL":   "debug",
        "ST2_AUTH_USERNAME": kwargs['username'],
        "ST2_AUTH_PASSWORD": password
      },
      "hubot::external_scripts": ["hubot-stackstorm"],
      "hubot::dependencies": {
        "hubot": ">= 2.6.0 < 3.0.0",
        "hubot-scripts": ">= 2.5.0 < 3.0.0",
        "hubot-stackstorm": ">= 0.1.0 < 0.2.0"
      },

      "users": {
        kwargs['username']: {
          "password": password,
          "shell": "/bin/bash",
          "uid": "1000",
          "gid": "robots",
          "managehome": True,
        }
      },
      "groups": {
        "robots": {
          "gid": "6000",
        }
      }
    }

    # TODO: a better than "isn't a binary" key validation
    if kwargs["selfsigned"] == "0":
      if istext(request.POST['file-publickey'].file) and istext(request.POST['file-privatekey'].file):
        config["st2::ssl_public_key"] = request.POST['file-publickey'].file.read()
        config["st2::ssl_private_key"] = request.POST['file-privatekey'].file.read()
      else:
        temp['keyfallback'] = True

    if kwargs["chatops"] == "example":
      config["hubot::adapter"] = "irc"
      config["hubot::env_export"].update({
        "HUBOT_IRC_SERVER":   "localhost",
        "HUBOT_IRC_ROOMS":    "#stackstorm",
        "HUBOT_IRC_NICK":     kwargs['username'],
        "HUBOT_IRC_UNFLOOD":  True
      })
      config["hubot::dependencies"]["hubot-irc"] = ">=0.2.7 < 1.0.0"
    elif kwargs["chatops"] == "irc":
      config["hubot::adapter"] = "irc"
      config["hubot::env_export"].update({
        "HUBOT_IRC_SERVER":   kwargs["irc-server"],
        "HUBOT_IRC_ROOMS":    kwargs["irc-rooms"],
        "HUBOT_IRC_NICK":     kwargs['username'],
        "HUBOT_IRC_UNFLOOD":  True
      })
      config["hubot::dependencies"]["hubot-irc"] = ">=0.2.7 < 1.0.0"
    elif kwargs["chatops"] == "flowdock":
      config["hubot::adapter"] = "flowdock"
      config["hubot::env_export"].update({
        "HUBOT_FLOWDOCK_API_TOKEN":       kwargs["flowdock-token"],
        "HUBOT_FLOWDOCK_LOGIN_EMAIL":     kwargs["flowdock-email"],
        "HUBOT_FLOWDOCK_LOGIN_PASSWORD":  kwargs['flowdock-password']
      })
      config["hubot::dependencies"]["hubot-flowdock"] = ">=0.7.6 < 1.0.0"
    elif kwargs["chatops"] == "slack":
      config["hubot::adapter"] = "slack"
      config["hubot::env_export"].update({
        "HUBOT_SLACK_TOKEN": kwargs["slack-token"]
      })
      config["hubot::dependencies"]["hubot-slack"] = ">=3.3.0 < 4.0.0"
    elif kwargs["chatops"] == "hipchat":
      config["hubot::adapter"] = "hipchat"
      config["hubot::env_export"].update({
        "HUBOT_HIPCHAT_JID": kwargs["hipchat-jid"],
        "HUBOT_HIPCHAT_PASSWORD": kwargs["hipchat-password"]
      })
      if kwargs["text-hipchat-domain"] != "":
        config["hubot::env_export"]["HUBOT_XMPP_DOMAIN"] = kwargs["text-hipchat-domain"]
      config["hubot::dependencies"]["hubot-hipchat"] = ">=2.12.0 < 3.0.0"
    elif kwargs["chatops"] == "xmpp":
      config["hubot::adapter"] = "xmpp"
      config["hubot::env_export"].update({
        "HUBOT_XMPP_USERNAME": kwargs["xmpp-username"],
        "HUBOT_XMPP_PASSWORD": kwargs["xmpp-password"],
        "HUBOT_XMPP_ROOMS": kwargs["xmpp-rooms"]
      })
      if kwargs["xmpp-host"] != "":
        config["hubot::env_export"]["HUBOT_XMPP_HOST"] = kwargs["xmpp-host"]
      if kwargs["xmpp-port"] != "":
        config["hubot::env_export"]["HUBOT_XMPP_PORT"] = kwargs["xmpp-port"]
      config["hubot::dependencies"]["hubot-xmpp"] = ">=0.1.16 < 1.0.0"

    if not os.path.exists(path):
      os.makedirs(path)

    with open(path+filename, 'w') as workroom:
      workroom.write(json.dumps(config))

    return temp
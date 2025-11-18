# Bot_Status 

## 邮箱通知配置
要想使用指令首先需要配置好在 [.env](/.env#L3) 中配置好 SUPERUSERS

离线邮箱通知会向BotConfig中设置好的admin与 [.env](/.env#L128) 中设置的邮箱发送邮件，因此想给号主发邮件,请给牛牛配置好admins。

没有给Bot配置admins的请使用 [config.mongodb](/tools/config.mongodb) 来为牛牛添加她的号主账号。

邮箱配置请参考各邮箱的smtp配置。

配置好邮箱后发送 `测试邮件` 可以测试邮箱配置是否成功。
# Risks of using PaperDaemon

PaperDaemon asks you to acknowledge these risks the first time it opens. Please read them before you use it.

**It is unofficial.** PaperDaemon is an independent, third-party application. It is not made, endorsed or supported by
reMarkable. It is meant to make an unmodified reMarkable tablet more useful: nothing is installed on the tablet, and
it works only through reMarkable's cloud, as the reMarkable desktop app does.

**It uses your reMarkable login.** PaperDaemon signs in with the login of the reMarkable desktop app on your PC. It
borrows it, so the two share it and only one runs at a time, or it takes it, which signs the desktop app out.
reMarkable may not allow this. They could block it, act on the account, or change their app or cloud so PaperDaemon
stops working.

**It writes to your notebooks.** I can't guarantee PaperDaemon will never damage one of your notebooks. PaperDaemon
checks each page in the cloud before writing it, and never writes over newer work from the tablet. PaperDaemon keeps
copies of the pages it changes on your PC. It was tested thoroughly on a reMarkable Paper Pro running software
3.29.1.0 - tablet software updates may break PaperDaemon, proceed at your own risk.

**Your pages go to the models you choose.** A model running on your own PC keeps them on your PC. A service you give
an API key receives what each job needs, under that service's own terms.

**There is no warranty.** PaperDaemon is provided as is, without warranty of any kind, under the
[Apache License 2.0](LICENSE). I am not responsible for what anyone does with PaperDaemon, or for any loss or damage
it causes to notebooks, accounts, data or anything else.

reMarkable is a trademark of reMarkable AS. PaperDaemon uses the name only to say which tablet it works with.

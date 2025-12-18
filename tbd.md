[x] need to parameterize speeds such as v1, v2, rotate speed, etc.
[x] Need to fix the speech output icon
[x] Need to create a timeline or stack of action
[x] Need to create a full electronic checklist implementation
[x] Need to fix the glowing (2 quick tap is ok)
[x] Need to think of an override button
[x] Need to define exactly the behaviour of CHECK, CANCEL, ALLOW, DENY, OVERRIDE
[x] Need to finish implementing the interaction panel
[x] Need to add AGMEB to FMS to continue straight ahead
[x] Screenshot Jeppesen shows that departure is cleared straight ahead 5000ft for Jet aircraft
[x] Engine failure or fire or master warning or any other non-normal event during takeoff checklist clearly shows 1. CLIMB TO A SAFE ALTITUDE. So TARS need to help climbing (pallier d'acceleration 1500ft agl, vitesse d'acceleration Venr) ==> Engine FIRE
[x] Remove trimming alarm, use as cautionary tale
[ ] Add a reclaim vs offload button
[x] Add tars input composante de vent de travers sur checkwind
[x] How to set/ensure the frequencies for panpan/mayday call?
[x] The tars input should be boxed to look more like an output
[ ] Remove aviate tasks such as brakes hold.
[x] Create a version with only the interaction panel, as a new page
[x] Agentify the interface
[ ] Add NLP for ATC
[ ] when user approve/deny/check/cancel, the feedback should be immediate, --> next state
[ ] Speed up the TTS a bit
[ ] Need to wrap the Aircraft agent to be able to kill x-plane and relaunch it automatically to get rid of any cache-related issues (there is a possibility that dev reload aircraft work fine) 
[ ] The ATC agent should run with the SIM, Facilitator should be able to send without delays
[ ] add "Okay" to voice command
[ ] Fix the trim
[ ] Check why select altitude is skipped (bug)
[ ] The Master warming acknowledgement should be in redundancy in the GUI (i.e if you click the ack engine fire rather than click the physical attention getter you should get to the next state, don't block the user)
[ ] Abandon all navigation tasks
[ ] Fix fuel boost OFF/NORM bs. Also because it goes off then norm you get the message from TARS that you switched the wrong button but that's false.
[ ] Check should be a button trigger (but not approve)
[ ] STT/TTS should be part of shared interface
[ ] AP ON + trim + counter 30s should be independent of the FSM in a dedicated thread
[ ] We need to be able to activate/deactivate help

[ ] Add attention getter web agent
[ ] Add Tutorial for flight scenario with imm act item, and TARS interaction
[ ] Get access to the flight panel of the flight sim
[ ] allow the motion
[ ] Set up eye-tracking cameras
[ ] if unable to get camera feed from the eye tracker retrieve the feed from the webcam
[ ] How to evaluate workload ? 
[ ] 

In windows if pyttsx3 is in a subprocess it will take the first queued message but never finish it, we need to treat pyttsx3 as the shared interface GUI, it should have an input somewhere like tts_input and TARS core sends string through it.


For the task taxonomy and workflow, in the HAT simulation, to compare workflows we need to have a real distinction between task execution
for instance
Check winds, if performer==human and supporter is automatically added then the performer==TARS doesn't "add" any new config, because in that case TARS cannot jump by itself to the next task, it is not autonomous, so we could say it's orange in performer but it doesn't add any new information, might as well just consider tars is a possible supporter.
So in my use case, I don't really understand the orange color coding... my though is that if it's orange then it's not autonomous then it's not a performer

The fact that TARS is a memory aid is a de-facto yellow support... Analys need to choose to represent that or not.
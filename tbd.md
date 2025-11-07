[x] need to parameterize speeds such as v1, v2, rotate speed, etc.
[x] Need to fix the speech output icon
[x] Need to create a timeline or stack of action
[x] Need to create a full electronic checklist implementation
[ ] Need to fix the glowing
[ ] Need to think of an override button
[ ] Need to define exactly the behaviour of CHECK, CANCEL, ALLOW, DENY, OVERRIDE
[ ] Need to finish implementing the interaction panel


this is the behaviour of the FSM for one example 

        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.is_fadec_bug_to, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].callout) if self.states[("TAKEOFF", "\"Thrust set\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.states[("TAKEOFF", "\"Thrust set\"", "ANNOUNCE")], 
            self.is_engine_spool_even, 
            self.dummy_action))

this means there is a transition for FADEC bug CHECK TO --> to Engine Spool CHECK EVEN
when entering Engine spool check even State the fsm will wait delay_before_action then fire the lambda whatever the condition, it is an entering state function
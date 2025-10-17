Right now the application is waiting for an emergency to happen which makes no sense even though the scenario is always of an engine failure, because the onset of the bird strike can vary the agent needs to have a NOMINAL STATE that can be changed to NON-NOMINAL then emergency

MetaState.default = NOMINAL
IF Master warning || Master caution || Engine fire L || engine fire Right
Metastate = EMERGENCY 
while(emergency.procedure is not finished)
{

}
emergency.procedure = NON-NOMINAL
while(non-nominal.procedure is not finished)
{

}
Metastate = NOMINAL

That means I need to enrich the task allocation table with the new states and transitions (it was previously modeled only for the emergency scenario)

[ ] need to parameterize speeds such as v1, v2, rotate speed, etc.
[ ] Need to fix the speech output icon
[ ] Need to create a timeline or stack of action
[ ] Need to create a full electronic checklist implementation


# How the IA.csv work

- interaction : A string that will be switched to know what to display in the dedicated interaction window
- time_init_action : The time between entering the state and executing the action (for instance contact ATC in 5, 4, 3, ...)
- time_end_action : The time between executing the action and being allowed to transition to the next state to prevent very fast state changing
- callout : The phrase that needs to be said for this action 
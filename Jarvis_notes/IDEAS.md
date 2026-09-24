---
updated: "2026-09-23T19:06:41Z"
index_state: "indexed_local"
content_hash: "0eec55f0806710cbc0e79ba2839d84c4ab455881a0d30c0c3be59fbe3b1f88f9"
---

## Agent Builder

I was recently using the open ai api platform, and on their webpage for "agent building" they used what looked like a canvas to create a "workflow", This is good as it allows the user to clearly see what the agent will be doing and/or instructed to do at the time. 
![[Pasted image 20260918094635.png]]

Here we can see an example of the workflow that could be provided.  by using different tile colours and icons its clear to see the functions of each note, the only improvement i'd offer here is a clear way to see that the reasoning note (yellow), is linked to the action note (white with icon). 
In obsidian this could be done by placing a directionless arrow between the two and a directional arrow to the subsequent action. 

![[Pasted image 20260918094804.png]]
![[Pasted image 20260918095130.png]]
![[Pasted image 20260918095142.png]]![[Pasted image 20260918095154.png]]![[Pasted image 20260918095210.png]]![[Pasted image 20260918095229.png]]![[Pasted image 20260918095244.png]]![[Pasted image 20260918095319.png]]
![[Pasted image 20260918095332.png]]![[Pasted image 20260918095343.png]]
![[Pasted image 20260918095354.png]]![[Pasted image 20260918095405.png]]

by using canvas notes to map out a workflow using each of these classifiers to create a representation for what the agent should be doing. 
to do this, we could convert the workflow into a .json workflow. 
here is an example of the type of workflow that could be created
[[example workflow planner.canvas]]

the idea im thinking of is that we use the canvas created to create a user level representation of the workflow desired, then via a compiling process that relies on a model capable of reasoning about the task to compile the workflow into actual agent instructions / plan.

# Auto Video Player
## Features to implement:
	1. Right click the video for a context menu with all options currently displayed in the bottom menu except the progress bar
		1. Control bar:
			1. Progress bar
			2. Loop toggle
			3. Mute toggle
			4. Volume slider
		2. Context menu:
			1. Mute toggle [DONE]
			2. Loop toggle [DONE]
			3. Play order (single selection) [new feature]
				1. Shuffle
				2. Name
				3. Date Modified
			4. Media type (multi select) [new feature]
				1. Videos (mp4, mov, m4v, etc...)
				2. Pictures (jpg, jpeg, png, etc...)
				3. Gifs (gif)
			5. Select folder to play from [DONE]
			6. Open in File Explorer [DONE]
			7. Copy current video to... [DONE] (should this open the last play coppied to?)
			8. Select default folder to copy to and to play from (shoild they be different?)
	2. Make the video frame take up the entire window length and overlay the control bar on top of the video frame. Keep functinality for 
	   show/hide toggle of the control bar when the bottom of the window (not including the control bar itself) is clicked. [DONE]
	3. Default folders to open when selecting a folder and for when copying to.
	4. Ability to modify tags on the current video
	5. Add current file name to the window title
	6. Next/previous video transition should be seamless, there should be no black frames during the transition
	7. Connect volume slider to mute icon. UI elements should stay together when resizing the window. when icon is muted, volume slider goes
				to 0. When icon is unmuted, sloder goes to value before it was muted. when volume slider is moved, the icon changes. 
			

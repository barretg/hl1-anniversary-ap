## What's New

* Added Blue Shift Campaign
  * NOTE: Host must own the game.
* Added Opposing Force Campaign
  * NOTE: Host must own the game.
* Added They Hunger Campaign
* Various logic and stability improvements
* New YAML Option to disable all intro missions
* Starting weapon is now randomized between all enabled campaign's melee weapons (excludes reskins like the knife, shovel, and umbrella as these are map specific)
* Traps now queue so they always get you even if you're mid level load :)
* New commands: `!tracker <text>` and `!find <text>`
  * The `!tracker` command can be used to display a checklist of checks for all or some missions (matches on the text argument)
  * The `!find` command can be used to see roughly how far you are from the nearest check location within the same map, or a specific location provided by text argument in the same map or another.
* Updated command: `!warp`
  * Now lets you warp back to individual maps you've reached within a chapter so you don't always have to start at the beginning
* Console variants of all commands using `.ap` or `.ap_<cmd>`
* Updated weapon locations and added locations for HEV Suit pickups in all campaigns that have an HEV Suit equivalent

## Known Issues
* General instability: expect some crashing or other random issues
* Sound cacheing bug: sometimes when another player joins the lobby, their sounds are all mixed up. This will self resolve once you get into a mission. I am under the impression that if they install the plugin too that helps, but I'm unsure. This one is kind of complicated to diagnose.
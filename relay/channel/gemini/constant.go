package gemini

var ModelList = []string{
	"gemini-3.1-pro-preview",
	"gemini-3.1-pro-preview-customtools",
	"gemini-3.1-flash-lite-preview",
	"gemini-3.1-flash-image-preview",
	"nano-banana-pro-preview",
}

var SafetySettingList = []string{
	"HARM_CATEGORY_HARASSMENT",
	"HARM_CATEGORY_HATE_SPEECH",
	"HARM_CATEGORY_SEXUALLY_EXPLICIT",
	"HARM_CATEGORY_DANGEROUS_CONTENT",
	//"HARM_CATEGORY_CIVIC_INTEGRITY", This item is deprecated!
}

var ChannelName = "google gemini"

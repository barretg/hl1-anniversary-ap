#include "hud.h"
#include "cl_util.h"
#include "com_model.h"
#include "cl_entity.h"

#include "ap_whiteboard.h"

#include <windows.h>
#include <gl/GL.h>

#include <cstdio>
#include <cstring>
#include <vector>

namespace {

// `kHubMap` in game/src/ap_hub.cpp, as the engine names the level.
const char* const kLobbyLevel = "maps/ap_lobby_alpha.bsp";
const char* const kBoardTexture = "poster15";
// wb00.tga, wb01.tga, ... as tools/build_whiteboards.py writes them.
const char* const kImageFormat = "gfx/whiteboards/wb%02d.tga";
constexpr int kMaxImages = 100;

// Not in GL 1.1's header. Core since 1.4, which every GoldSrc renderer has.
constexpr GLenum kGenerateMipmap = 0x8191;

// The GL renderer's texture_t. The SDK's com_model.h describes the software
// one, which has no texture name; the hardware engine carries it right after
// the size. Only the leading fields are read, and a wrong guess is caught by
// glIsTexture rather than trusted.
struct GLTexture
{
	char name[16];
	unsigned width, height;
	int gl_texturenum;
};

struct Image
{
	int width = 0;
	int height = 0;
	std::vector<unsigned char> rgba;
};

bool g_pending = false;
int g_imageCount = -1;
// The texture we drew over and what it held before, so a later map that
// shares poster15 through the engine's texture cache gets the poster back.
GLuint g_touched = 0;
Image g_original;

// An uncompressed 24 or 32-bit TGA, as top-down RGBA.
bool LoadTGA(const char* path, Image& out)
{
	int length = 0;
	byte* data = gEngfuncs.COM_LoadFile(const_cast<char*>(path), 5, &length);
	if (!data)
		return false;

	bool ok = false;
	if (length >= 18 && data[2] == 2 && (data[16] == 24 || data[16] == 32))
	{
		const int width = data[12] | (data[13] << 8);
		const int height = data[14] | (data[15] << 8);
		const int bpp = data[16] / 8;
		const bool topDown = (data[17] & 0x20) != 0;
		const byte* pixels = data + 18 + data[0];
		if (width > 0 && height > 0 && pixels + width * height * bpp <= data + length)
		{
			out.width = width;
			out.height = height;
			out.rgba.resize(width * height * 4);
			for (int y = 0; y < height; ++y)
			{
				const byte* src = pixels + (topDown ? y : height - 1 - y) * width * bpp;
				unsigned char* dst = &out.rgba[y * width * 4];
				for (int x = 0; x < width; ++x, src += bpp, dst += 4)
				{
					dst[0] = src[2];
					dst[1] = src[1];
					dst[2] = src[0];
					dst[3] = bpp == 4 ? src[3] : 255;
				}
			}
			ok = true;
		}
	}
	gEngfuncs.COM_FreeFile(data);
	return ok;
}

bool ImageExists(int index)
{
	char path[64];
	snprintf(path, sizeof(path), kImageFormat, index);
	int length = 0;
	byte* data = gEngfuncs.COM_LoadFile(path, 5, &length);
	if (!data)
		return false;
	gEngfuncs.COM_FreeFile(data);
	return true;
}

GLTexture* FindBoard(model_t* world)
{
	for (int i = 0; i < world->numtextures; ++i)
	{
		GLTexture* texture = reinterpret_cast<GLTexture*>(world->textures[i]);
		if (texture && !stricmp(texture->name, kBoardTexture))
			return texture;
	}
	return nullptr;
}

void Upload(GLuint texnum, const Image& image)
{
	GLint previous = 0;
	glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous);
	glBindTexture(GL_TEXTURE_2D, texnum);
	glTexParameteri(GL_TEXTURE_2D, kGenerateMipmap, GL_TRUE);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0,
		GL_RGBA, GL_UNSIGNED_BYTE, image.rgba.data());
	// The engine tracks its own last bind and skips redundant ones.
	glBindTexture(GL_TEXTURE_2D, previous);
}

void SaveOriginal(GLuint texnum)
{
	GLint previous = 0;
	glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous);
	glBindTexture(GL_TEXTURE_2D, texnum);
	GLint width = 0, height = 0;
	glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH, &width);
	glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT, &height);
	g_original = Image();
	if (width > 0 && height > 0)
	{
		g_original.width = width;
		g_original.height = height;
		g_original.rgba.resize(width * height * 4);
		glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA, GL_UNSIGNED_BYTE, g_original.rgba.data());
	}
	glBindTexture(GL_TEXTURE_2D, previous);
}

void Apply(model_t* world)
{
	GLTexture* board = FindBoard(world);
	if (!board)
		return;

	const GLuint texnum = static_cast<GLuint>(board->gl_texturenum);
	if (!glIsTexture(texnum))
	{
		gEngfuncs.Con_DPrintf("AP: whiteboard: no GL texture for %s, left as is\n", kBoardTexture);
		return;
	}

	const char* level = gEngfuncs.pfnGetLevelName();
	if (stricmp(level, kLobbyLevel))
	{
		// Another map with the stock poster, and the engine handed it the
		// texture we drew on.
		if (texnum == g_touched && !g_original.rgba.empty())
			Upload(texnum, g_original);
		return;
	}

	if (g_imageCount < 0)
	{
		g_imageCount = 0;
		while (g_imageCount < kMaxImages && ImageExists(g_imageCount))
			++g_imageCount;
	}
	if (g_imageCount == 0)
		return;

	const int pick = gEngfuncs.pfnRandomLong(0, g_imageCount - 1);
	char path[64];
	snprintf(path, sizeof(path), kImageFormat, pick);
	Image image;
	if (!LoadTGA(path, image))
	{
		gEngfuncs.Con_DPrintf("AP: whiteboard: could not read %s\n", path);
		return;
	}

	if (texnum != g_touched)
	{
		SaveOriginal(texnum);
		g_touched = texnum;
	}
	Upload(texnum, image);
}

} // namespace

void APWhiteboard_VidInit()
{
	g_pending = true;
}

void APWhiteboard_Frame()
{
	if (!g_pending)
		return;
	cl_entity_t* worldEntity = gEngfuncs.GetEntityByIndex(0);
	model_t* world = worldEntity ? worldEntity->model : nullptr;
	if (!world || !world->textures)
		return;
	g_pending = false;
	Apply(world);
}

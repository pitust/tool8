#!/usr/bin/env python3
# romangle: a small tool to convert raw assets (faces, roms, keymaps etc.) into rom8 file(s) automatically.

import argparse, enum, sys, struct, json, re, os
from os.path import basename
def run():
	if len(sys.argv) == 1:
		for k, v in list(globals().items()):
			if k.startswith('cmd_'):
				vc = v.__code__
				kwd = v.__kwdefaults__
				if kwd == None:
					kwd = {}
				assert vc.co_argcount == 0
				assert vc.co_posonlyargcount == 0
				items = []
				for arg in vc.co_varnames[:vc.co_kwonlyargcount]:
					if arg in kwd:
						items.append('[--%s=VALUE]' % arg)
					else:
						items.append('--%s=VALUE' % arg)
				print('Usage: romangle %s %s' % (k[4:], ' '.join(items)))
	else:
		for k, func in list(globals().items()):
			if k == 'cmd_' + sys.argv[1]:
				argdict = {}
				vc = func.__code__
				kwd = func.__kwdefaults__
				if kwd == None:
					kwd = {}
				assert vc.co_argcount == 0
				assert vc.co_posonlyargcount == 0
				
				allowed, required = [], []
				for arg in vc.co_varnames[:vc.co_kwonlyargcount]:
					allowed.append(arg)
					if arg not in kwd:
						required.append(arg)

				is_val = False
				for ent in sys.argv[2:]:
					if is_val:
						if is_val in argdict.keys():
							argdict[is_val] += ',' + ent
						else:
							argdict[is_val] = ent
						is_val = False
						continue
					else:
						if ent.startswith('--'):
							ent = ent[1:]
						assert ent.startswith('-'), 'invalid value {}'.format(ent)
						if '=' in ent:
							k, v = ent[2:].split('=')
							if k in argdict.keys():
								argdict[k] += ',' + v
							else:
								argdict[k] = v
						else:
							is_val = ent[1:]
				assert not is_val, 'expected value for argument {}'.format(is_val)
				for k in argdict:
					assert k in allowed, 'invalid argument {}'.format(k)
				for r in required:
					assert r in argdict, 'missing required argument {}'.format(r)
				func(**argdict)
				break
		else:
			print('E: invalid subcommand %s' % sys.argv[1])

class ROM8Tag(enum.IntEnum):
	end = 0
	compatible = enum.auto()
	prop = enum.auto()
	rom = enum.auto()
	faceSVG = enum.auto()
	facePNG = enum.auto()
	faceDisplayBounds = enum.auto()
	faceGUIKeys = enum.auto()
	faceKeymap = enum.auto()
	calcType = enum.auto()
	faceKeybinds = enum.auto()
class CalcType(enum.IntFlag):
	old = 1
	cwi = 2
	cwii = 3
	type_mask = 3
	emu = 4
class write8:
	def __init__(self, file) -> None:
		self.fd = open(file, 'wb')
	def __enter__(self):
		self.write(ROM8Tag.compatible, SUPPORTED_ROM8)
		return self
	def __exit__(self, *_):
		self.write(ROM8Tag.end, b'')
		self.fd.close()
	def write(self, tag, pay):
		self.fd.write(struct.pack('<II', int(tag), len(pay)))
		self.fd.write(pay)
	def prop(self, k, v):
		self.write(ROM8Tag.prop, b'%s=%s' % (k.encode(), v.encode()))

SUPPORTED_ROM8 = b'pitust,2'
assets = {}

def identify(fn):
	fn = basename(fn)
	if fn == 'keylog.json':
		return 'officialKeyNames'
	if fn.endswith('.svg'):
		return 'faceSVG'
	if fn == 'face.html':
		return 'officialHitboxAttrib'
	if fn.endswith('.bin'):
		return 'rom'
	if fn.endswith('.dump'):
		return 'romDump'
	if fn == 'index.html':
		return 'ignore'
	return 'unknown'
def scan(f):
	if os.path.isdir(f):
		for de in os.listdir(f):
			scan('%s/%s' % (f, de))
	else:
		match = re.findall(r'[EC]Y-?[0-9]{3}', f)
		if len(match):
			nm = match[0].replace('-', '')
			if nm not in assets:
				assets[nm] = {}
			t = identify(f)
			if t == 'ignore':
				return
			if t == 'unknown':
				print('W: unknown file %s' % f)
				return
			assets[nm][t] = open(f, 'rb').read()

def fromkio(ki, ko):
	assert (ki-1)&ki == 0
	assert (ko-1)&ko == 0

	ki = (ki-1).bit_count()
	ko = (ko-1).bit_count()
	kc = (ki<<4)|ko
	return kc

def cmd_mangle(*, i, o = 'roms'):
	rompath = o
	if '%s' not in rompath:
		rompath += '/%s.rom8'

	for idir in i.split(','):
		scan(idir)
	for id, props in assets.items():
		if 'rom' not in props and 'romDump' not in props:
			print('E: %s has no rom available' % id)
			continue
		for romId, emuFlags, emuLabel, labelPath in [('rom', CalcType.emu, ' (emu)', '-emu'), ('romDump', 0, '', '-real')]:
			if romId not in props:
				continue
			with write8(rompath % (id + labelPath)) as wr:
				wr.prop('model', id + emuLabel)
				wr.prop('writer', 'romangle')
				wr.prop('writer.repo', 'https://git.malwarez.xyz/~pitust/romangle')
				wr.write(ROM8Tag.rom, props['rom'])
				wr.write(ROM8Tag.calcType, bytes([(CalcType.cwi if 'CY' in id else CalcType.cwii) | emuFlags]))
				if 'faceSVG' in props:
					svg = props['faceSVG'].decode()
					svg = svg.replace('width="376" height="635" viewBox="0 0 376 635"', 'width="375" height="635" viewBox="0 0 375 635"')
					print(id, svg.split('\n')[0])
					assert 'width="375" height="635" viewBox="0 0 375 635"' in svg
					
					svg = svg.replace('width="375" height="635" viewBox="0 0 375 635"', 'width="750" height="1270" viewBox="0 0 375 635"')
					wr.write(ROM8Tag.faceSVG, svg.encode())

					x, y = 87, 111
					w, h = 96, 31
					scale = 6
					wr.write(ROM8Tag.faceDisplayBounds, struct.pack('<HHHH H', x, y, w, h, scale))
				if 'officialKeyNames' in props:
					keybinds = b''
					keymap = b''
					for kio, (_, key, text) in json.loads(props['officialKeyNames']).items():
						ki, ko = kio.split(',')
						kc = fromkio(int(ki), int(ko))
						keymap += bytes([kc]) + text.encode() + b'\x00'
						if len(key) == 1:
							keybinds += key.encode() + bytes([kc])
					if keybinds != b'':
						wr.write(ROM8Tag.faceKeybinds, keybinds)
					if keymap != b'':
						wr.write(ROM8Tag.faceKeymap, keymap)
				if 'officialHitboxAttrib' in props:
					keybinds = b''
					for ki, ko, x, y, w, h in re.findall(
						r"<div .+ data-ki=\"([0-9]+)\" data-ko=\"([0-9]+)\" style=\"left: ([0-9\.]+)px; top: ([0-9\.]+)px; width: ([0-9\.]+)px; height: ([0-9\.]+)px;\">",
						props['officialHitboxAttrib'].decode()
					):
						x = int(float(x) * 2)
						y = int(float(y) * 2)
						w = int(float(w) * 2)
						h = int(float(h) * 2)
						kc = fromkio(int(ki), int(ko))
						keybinds += struct.pack('<HHHH H', x, y, w, h, kc)
					wr.write(ROM8Tag.faceGUIKeys, keybinds)
						
if __name__ == '__main__':
	run()

import React from 'react';
import {Composition} from 'remotion';
import {Film} from './Film';
import {Cover} from './Cover';
import {FPS, FRAMES} from './common/beats';
export const RemotionRoot: React.FC = () => <>
  <Composition id="Film" component={Film} durationInFrames={FRAMES} fps={FPS} width={1080} height={1920} />
  <Composition id="Cover916" component={Cover} defaultProps={{w: 1080, h: 1920}} durationInFrames={1} fps={FPS} width={1080} height={1920} />
  <Composition id="Cover43" component={Cover} defaultProps={{w: 1440, h: 1080}} durationInFrames={1} fps={FPS} width={1440} height={1080} />
</>;

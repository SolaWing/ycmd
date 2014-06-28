// Copyright (C) 2011, 2012  Google Inc.
//
// This file is part of YouCompleteMe.
//
// YouCompleteMe is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// YouCompleteMe is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

#include "LetterNodeListMap.h"
#include "standard.h"
#include <algorithm>

namespace YouCompleteMe {

const int kNumLetters = NUM_LETTERS;
//static const int kLettersIndexStart = 0;
//static const int kNumbersIndexStart = 26;
const int kUpperToLowerCount = 'a'-'A';

    // map char to range 0-63
const char charIndex[256] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,37,38,39,40,41,42,43,39,44,45,46,47,48,49,50,51,27,28,29,30,31,32,33,34,35,36,52,53,54,55,56,57,58,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,44,42,45,41,49,39,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,44,43,45,49,37};


int IndexForChar( char letter ) {
    return charIndex[(unsigned char)letter];
//  if (letter < ' ') return 0;
//  if (letter < 'A') return letter - ' ';
//  if (letter <= 'Z') letter += 'a' - 'A';
//  return letter - 58;
//  if ( IsUppercase( letter ) )
//    return letter + ( 'a' - 'A' );
//
//  return letter;
}


LetterNodeListMap::LetterNodeListMap() {
  std::fill( letters_.begin(),
             letters_.end(),
             static_cast< std::list< LetterNode * >* >( NULL ) );
}


LetterNodeListMap::~LetterNodeListMap() {
  for ( uint i = 0; i < letters_.size(); ++i ) {
    delete letters_[ i ];
  }
}


bool LetterNodeListMap::HasLetter( char letter ) {
  int letter_index = IndexForChar( letter );
  std::list< LetterNode * > *list = letters_[ letter_index ];
  return list;
}


std::list< LetterNode * > &LetterNodeListMap::operator[] ( char letter ) {
  int letter_index = IndexForChar( letter );
  std::list< LetterNode * > *list = letters_[ letter_index ];

  if ( list )
    return *list;

  letters_[ letter_index ] = new std::list< LetterNode * >();
  return *letters_[ letter_index ];
}


std::list< LetterNode * > *LetterNodeListMap::ListPointerAt( char letter ) {
  return letters_[ IndexForChar( letter ) ];
}


bool LetterNodeListMap::HasLetter( char letter ) const {
  return letters_[ IndexForChar( letter ) ] != NULL;
}

} // namespace YouCompleteMe
